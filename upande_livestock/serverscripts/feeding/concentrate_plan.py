# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What concentrate the farm has, and what it must mix to cover the week.

The farm mixes concentrate weekly and feeds the TMR twice a day out of it, so
the question on a Monday is not "what does this herd need today" but "what do I
put through the mixer to get to next Monday". That is one number per
concentrate, and it is a sum over every herd that eats it.

Demand is read off the herds, not typed in: for each herd, the concentrate line
in its ration times its head count times the days. So a herd that grows, or a
ration that changes, moves the plan without anyone editing a figure. Which is
the point — the last time this was carried by hand the weaner herd was asking
for 45 tonnes a day.

Stock is what the mixer can draw on, so it counts every warehouse the item sits
in rather than one store. `to_mix` is what remains after that, rounded up to
whole batches because the recipes are stated per 1000 kg and a mixer does not
run a fifth of a batch on purpose — `batches` is the honest number and
`to_mix_kg` is what it produces.

`can_mix` says whether the raw materials are actually there. A plan that says
"mix 6.3 tonnes" while the store has no canola is worse than no plan, because
it looks like a decision has been made.

`lines` is the recipe ONE BATCH at a time — the BOM as written, unscaled — and
`batch_qty`/`batch_uom` beside it say what those lines make. That is the
choice, and it is deliberate: a concentrate BOM is a batch recipe stated per
1000 kg, the mixer is loaded one batch at a time, and `batches` already says
how many times to load it. Scaling the lines to `to_mix_kg` would print
quantities nobody ever weighs out — and for a row needing four batches it would
read as one enormous load. The payload names the batch so the page cannot show
the lines under the run total by accident; multiply by `batches` for the week's
raw material draw, which is what `short` already reports.

Lines are in RECIPE qty/uom (`BOM Item.qty`/`.uom`), never stock units — the
same rule the ration picker and the ration history follow, and for the same
reason: hay is written in kg and stocked in BALE at cf 0.07.

Read-guarded on Item — it discloses stock balances across the farm.
"""

import math

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding import _engine as feeding
from upande_livestock.serverscripts.feeding import _recipe_lines

DEFAULT_DAYS = 7
BATCH_KG = 1000.0


def _herd_demand(days):
	"""Concentrate item -> {herds that eat it, kg needed over `days`}."""
	demand = {}
	for herd in frappe.get_all("Herds", filters=[["bom", "is", "set"]], pluck="name"):
		try:
			_doc, bom, heads = feeding._herd_bom(herd)
		except Exception:
			continue
		if not heads:
			continue
		for row in frappe.get_all(
			"BOM Item", filters={"parent": bom.name}, fields=["item_code", "qty", "bom_no"]
		):
			# A concentrate is a line with a recipe of its own. A raw material —
			# silage, hay — has none, and is not mixed.
			sub = row.bom_no or frappe.db.get_value("Item", row.item_code, "default_bom")
			if not sub:
				continue
			entry = demand.setdefault(
				row.item_code,
				{"item_code": row.item_code, "herds": [], "per_day_kg": 0.0, "bom_no": sub},
			)
			per_day = flt(row.qty) * heads
			# per-head kg x head count, for each day
			entry["per_day_kg"] += per_day
			entry["herds"].append({"herd": herd, "heads": heads, "per_head_kg": flt(row.qty)})
	for entry in demand.values():
		entry["needed_kg"] = entry["per_day_kg"] * days
	return demand


def _on_hand(item_code):
	return flt(
		frappe.db.sql(
			"SELECT IFNULL(SUM(actual_qty), 0) FROM tabBin WHERE item_code = %s", (item_code,)
		)[0][0]
	)


def _raw_shortfall(bom_no, produce_kg):
	"""Whether the store can cover mixing `produce_kg` from this recipe."""
	if not bom_no or produce_kg <= 0:
		return []
	try:
		_bom, lines = feeding.resolve_requirement(bom_no, produce_kg)
	except Exception:
		return []
	return [
		{
			"item_code": ln["item_code"],
			"item_name": ln.get("item_name"),
			"required_qty": ln["required_qty"],
			"available": ln.get("available"),
			"short_qty": ln["short_qty"],
		}
		for ln in lines
		if flt(ln.get("short_qty")) > 0
	]


def _batch_sizes(bom_nos):
	"""{bom_no: row} carrying what one batch of each recipe makes.

	`BOM.quantity`/`uom`, not the BATCH_KG constant: the constant is what the
	plan rounds up to, this is what the recipe itself says it produces, and a
	row's `lines` are only readable next to the number they make.
	"""
	wanted = sorted({name for name in (bom_nos or []) if name})
	if not wanted:
		return {}
	return {
		row.name: row
		for row in frappe.get_all(
			"BOM", filters={"name": ["in", wanted]}, fields=["name", "quantity", "uom"]
		)
	}


@frappe.whitelist()
def concentrate_plan(days=DEFAULT_DAYS):
	def go():
		guard_read("Item")
		# `or DEFAULT_DAYS` would swallow a deliberate 0 — flt(0) is falsy — and
		# quietly answer for a week instead of refusing.
		span = DEFAULT_DAYS if days in (None, "") else int(flt(days))
		if span <= 0:
			frappe.throw(frappe._("A plan has to cover at least one day."))

		demand = _herd_demand(span)
		# One query for every recipe on the page and one for their batch sizes.
		# There are five concentrates on this site, but a loop of per-row
		# fetches is a loop either way.
		bom_nos = [entry["bom_no"] for entry in demand.values()]
		lines_by_bom = _recipe_lines.lines_for(bom_nos)
		batch_of = _batch_sizes(bom_nos)

		rows = []
		for code, entry in sorted(demand.items()):
			on_hand = _on_hand(code)
			to_mix = max(entry["needed_kg"] - on_hand, 0.0)
			batches = math.ceil(to_mix / BATCH_KG) if to_mix > 0 else 0
			to_mix_kg = batches * BATCH_KG
			short = _raw_shortfall(entry["bom_no"], to_mix_kg)
			batch = batch_of.get(entry["bom_no"])
			rows.append(
				{
					"item_code": code,
					"item_name": frappe.db.get_value("Item", code, "item_name") or code,
					"bom_no": entry["bom_no"],
					# The recipe for ONE batch, in recipe units, with the batch it
					# makes named beside it. See the module docstring.
					"lines": lines_by_bom.get(entry["bom_no"], []),
					"batch_qty": flt(batch.quantity) if batch else 0.0,
					"batch_uom": (batch.uom if batch else "") or "",
					"per_day_kg": round(entry["per_day_kg"], 2),
					"needed_kg": round(entry["needed_kg"], 2),
					"on_hand_kg": round(on_hand, 2),
					"to_mix_kg": to_mix_kg,
					"batches": batches,
					"days_cover": round(on_hand / entry["per_day_kg"], 1)
					if entry["per_day_kg"]
					else None,
					"can_mix": not short,
					"short": short,
					"herds": entry["herds"],
				}
			)
		return {
			"ok": True,
			"days": span,
			"batch_kg": BATCH_KG,
			"concentrates": rows,
			"total_to_mix_kg": sum(r["to_mix_kg"] for r in rows),
			"total_batches": sum(r["batches"] for r in rows),
		}

	return run(go, "livestock concentrate_plan failed")
