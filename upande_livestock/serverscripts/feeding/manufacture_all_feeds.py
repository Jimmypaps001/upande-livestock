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

When the switch is on, the concentrates those rations consume that the store
cannot cover are mixed first, in whole batches, by the same `_concentrate_plan`
the Feeding page uses. When it is off there is no concentrate stage at all.

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
from upande_livestock.serverscripts.feeding._concentrate import premanufacture_concentrate_on

TOLERANCE = 0.0005


def _plan_herds(day, portion):
	"""([run, ...], [skipped, ...]) for `day`. Reads only."""
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
		if remaining <= TOLERANCE:
			skipped.append({"herd": h.name, "reason": "already fully fed"})
			continue
		# Never more than what is left of the day.
		share = min(flt(portion) or 1.0, remaining / day_qty)
		runs.append(
			{
				"herd": h.name, "bom": h.bom, "item": bom.item, "heads": heads,
				"portion": round(share, 4),
				"qty": feeding.manufacture_qty(per_head, heads, share),
				"day_qty": day_qty, "issued": issued,
			}
		)
	return runs, skipped


def _plan_concentrates(runs):
	"""The concentrates to mix before the herds, in whole batches. Reads only.

	Needs are summed across herds against what the stores hold, so three herds
	that each fit on their own do not pass a check the three together fail.
	"""
	combined = {}
	for r in runs:
		_bom, lines = feeding.resolve_requirement(r["bom"], r["qty"])
		r["short"] = [
			{"item_code": ln["item_code"], "item_name": ln["item_name"], "short_qty": ln["short_qty"],
			 "uom": ln["uom"]}
			for ln in lines if ln["short_qty"] > 0
		]
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
def manufacture_all_feeds(date=None, portion=1.0, preview=0):
	def go():
		guard_stock("Work Order", "Stock Entry")
		day = getdate(date) if date else getdate(today())
		runs, skipped = _plan_herds(day, portion)
		on = premanufacture_concentrate_on()
		concentrates = _plan_concentrates(runs) if on else []
		if not on:
			for r in runs:
				_bom, lines = feeding.resolve_requirement(r["bom"], r["qty"])
				r["short"] = [
					{"item_code": ln["item_code"], "item_name": ln["item_name"],
					 "short_qty": ln["short_qty"], "uom": ln["uom"]}
					for ln in lines if ln["short_qty"] > 0
				]

		if cint(preview):
			return {
				"ok": True, "preview": True, "date": str(day),
				"premanufacture_concentrate": on,
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
			try:
				res = feeding.manufacture_herd_feed(
					r["herd"], portion=r["portion"],
					posting_date=str(day) if day != getdate(today()) else None,
				)
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
			"premanufacture_concentrate": on,
			"concentrates": made_concentrates, "herds": results, "skipped": skipped,
		}

	return run(go, "livestock manufacture_all_feeds failed")
