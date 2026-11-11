# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Mix every herd's ration for the day in one action.

Nothing new posts here. Each herd goes through `_engine.manufacture_herd_feed`,
the function behind `manufacture_feed`, under the same stock guard and the same
warn-not-block rule for a shortage (a run short today is recorded and its stock
waits as a draft transfer). This only decides WHICH herds to run, and for how
much, and puts the answers together.

Which herds: every herd with a standing ration and a fed head count above zero
that is not already fully fed for the day, by `feed_day_status`'s own reading of
the ledger (`_issues_on`). A herd part-fed is run for what is left, never the
whole portion again.

For the herds that use a pre-made concentrate (`Herds.concentrate_mode`, the
farm's Pre-manufacture Concentrate switch by default), the concentrates their
rations consume that the store cannot cover are mixed first, in whole batches,
by the same `_concentrate_plan` the Feeding page uses. Herds that mix from raw
have no concentrate stage at all, and when no herd pre-manufactures neither
does this.

With Feed by Head Count off (`_head_count`), head count x per head is only the
suggestion the preview offers. The operator's `totals` ({herd: kg}) are what
is mixed, and a herd with no total typed is left out rather than guessed at.

`preview=1` answers the same question without writing, so the confirmation
dialog lists exactly what the action would do.

One herd failing does not undo another: each herd runs under a savepoint and a
refusal is reported against that herd.
"""

import math

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from upande_livestock.serverscripts.common.envelope import guard_stock, run
from upande_livestock.serverscripts.feeding import _engine as feeding
from upande_livestock.serverscripts.feeding._concentrate import (
	premanufacture_by_herd,
	premanufacture_concentrate_on,
)
from upande_livestock.serverscripts.feeding._head_count import (
	clean_total,
	feed_by_head_count_on,
	portion_for_total,
)

TOLERANCE = 0.0005


def _plan_herds(day, portion, totals=None):
	"""([run, ...], [skipped, ...]) for `day`. Reads only.

	`totals` is None on a head-count farm. Otherwise it is the operator's
	{herd: kg}: each run carries the head-count figure as `suggested_qty` and
	the typed total as `qty`, and a herd the operator typed a total for is run
	even if the suggestion says it is already fed — they weighed it.
	"""
	from upande_livestock.serverscripts.common.calf_separation import fed_head_count
	from upande_livestock.serverscripts.feeding.feed_day_status import _issues_on

	runs, skipped = [], []
	herds = frappe.get_all("Herds", fields=["name", "bom"], order_by="name asc")
	for h in herds:
		if not h.bom:
			skipped.append({"herd": h.name, "reason": "no standing ration"})
			continue
		heads = fed_head_count(h.name)
		if heads <= 0:
			skipped.append({"herd": h.name, "reason": "no animals to feed"})
			continue
		bom = frappe.db.get_value("BOM", h.bom, ["item", "quantity"], as_dict=True)
		per_head = flt(bom.quantity) or 1.0
		day_qty = per_head * heads
		issued = sum(flt(r.qty) for r in _issues_on(bom.item, h.name, day))
		remaining = max(day_qty - issued, 0.0)
		typed = clean_total((totals or {}).get(h.name)) if totals is not None else None
		if remaining <= TOLERANCE and not typed:
			skipped.append({"herd": h.name, "reason": "already fully fed"})
			continue
		# Never more than what is left of the day.
		share = min(flt(portion) or 1.0, remaining / day_qty) if remaining > TOLERANCE else 0.0
		suggested = feeding.manufacture_qty(per_head, heads, share) if share else 0.0
		run_ = {
			"herd": h.name, "bom": h.bom, "item": bom.item, "heads": heads,
			"per_head": per_head,
			"portion": round(share, 4),
			"qty": suggested,
			"suggested_qty": suggested,
			"day_qty": day_qty, "issued": issued,
		}
		if typed:
			run_["qty"] = feeding.manufacture_qty(typed, 1, 1)
			run_["portion"] = round(portion_for_total(per_head, heads, typed), 4)
			run_["typed"] = True
		runs.append(run_)
	return runs, skipped


def _clean_totals(totals):
	"""{herd: kg} from whatever the page sent (a dict or its JSON)."""
	if not totals:
		return {}
	if isinstance(totals, str):
		totals = frappe.parse_json(totals)
	return {str(k): flt(v) for k, v in (totals or {}).items() if flt(v) > 0}


def _short_lines(lines):
	return [
		{"item_code": ln["item_code"], "item_name": ln["item_name"], "short_qty": ln["short_qty"],
		 "uom": ln["uom"]}
		for ln in lines if ln["short_qty"] > 0
	]


def _plan_concentrates(runs):
	"""The concentrates to mix before the herds, in whole batches. Reads only.

	Needs are summed across herds against what the stores hold, so three herds
	that each fit on their own do not pass a check the three together fail.
	"""
	combined = {}
	for r in runs:
		_bom, lines = feeding.resolve_requirement(r["bom"], r["qty"])
		r["short"] = _short_lines(lines)
		for ln in lines:
			if not (ln["is_concentrate"] and ln.get("bom_no")):
				continue
			got = combined.setdefault(ln["item_code"], {**ln, "required_qty": 0.0, "_avail": 0.0})
			got["required_qty"] += ln["required_qty"]
			got["_avail"] = max(got["_avail"], ln["available"])
	plans = []
	for item, line in combined.items():
		line["short_qty"] = max(0.0, line["required_qty"] - line.pop("_avail"))
		plan = feeding._concentrate_plan(line)
		if plan["needed"]:
			plans.append(
				{
					"item_code": item, "item_name": plan["item_name"], "bom_no": plan["bom_no"],
					"qty": plan["plan_qty"], "batches": plan["batches"], "uom": plan["uom"],
					"can_manufacture": plan["can_manufacture"],
					"shortages": [
						{"item_code": s["item_code"], "item_name": s["item_name"],
						 "short_qty": s["short_qty"], "uom": s["uom"]}
						for s in plan["shortages"]
					],
				}
			)
	return plans


@frappe.whitelist()
def manufacture_all_feeds(date=None, portion=1.0, preview=0, totals=None):
	def go():
		guard_stock("Work Order", "Stock Entry")
		day = getdate(date) if date else getdate(today())
		by_head = feed_by_head_count_on()
		typed = None if by_head else _clean_totals(totals)
		runs, skipped = _plan_herds(day, portion, typed)
		if not by_head and not cint(preview):
			# The operator's totals are what is mixed; a herd they left blank
			# is not fed a number they never saw.
			for r in [r for r in runs if not r.get("typed")]:
				skipped.append({"herd": r["herd"], "reason": "no total entered"})
			runs = [r for r in runs if r.get("typed")]

		farm_on = premanufacture_concentrate_on()
		mode = premanufacture_by_herd(farm_on)
		for r in runs:
			r["premanufacture"] = mode.get(r["herd"], farm_on)
		premade = [r for r in runs if r["premanufacture"]]
		# Only the herds that eat a made concentrate draw on one. A herd that
		# mixes from raw is priced line by line and plans no batch.
		concentrates = _plan_concentrates(premade) if premade else []
		for r in runs:
			if not r["premanufacture"]:
				_bom, lines = feeding.resolve_requirement(r["bom"], r["qty"])
				r["short"] = _short_lines(lines)

		if cint(preview):
			return {
				"ok": True, "preview": True, "date": str(day),
				"premanufacture_concentrate": farm_on,
				"feed_by_head_count": by_head,
				"concentrates": concentrates, "herds": runs, "skipped": skipped,
			}

		made_concentrates = []
		for c in concentrates:
			out = {"item_code": c["item_code"], "item_name": c["item_name"], "qty": c["qty"]}
			try:
				res = feeding.manufacture_concentrate(c["item_code"], qty=c["qty"], bom_no=c["bom_no"])
				out["work_order"] = res.get("work_order")
			except Exception as e:  # a short raw material is a warning here, not a stop
				frappe.db.rollback()
				out["warning"] = str(e)
			made_concentrates.append(out)

		results = []
		for r in runs:
			point = f"feed_all_{len(results)}"
			frappe.db.savepoint(point)
			entry = {"herd": r["herd"], "heads": r["heads"], "portion": r["portion"], "qty": r["qty"]}
			kwargs = {
				"portion": r["portion"] or 1.0,
				"posting_date": str(day) if day != getdate(today()) else None,
			}
			if r.get("typed"):
				kwargs["typed_total"] = r["qty"]
			try:
				res = feeding.manufacture_herd_feed(r["herd"], **kwargs)
				entry.update(
					status="waiting for stock" if res.get("pending") else "made",
					work_order=res.get("work_order"),
					produced_qty=res.get("produced_qty"),
					issued_qty=res.get("issued_qty"),
					uom=res.get("uom"),
				)
				warnings = []
				if res.get("waiting_for"):
					warnings.append(res["waiting_for"])
				elif r.get("short"):
					warnings.append(
						_("Short: {0}").format(", ".join(s["item_name"] for s in r["short"]))
					)
				entry["warnings"] = warnings
			except Exception as e:
				frappe.db.rollback(save_point=point)
				entry.update(status="error", error=str(e) or _("Operation failed."))
			results.append(entry)

		return {
			"ok": True, "preview": False, "date": str(day),
			"premanufacture_concentrate": farm_on,
			"feed_by_head_count": by_head,
			"concentrates": made_concentrates, "herds": results, "skipped": skipped,
		}

	return run(go, "livestock manufacture_all_feeds failed")
