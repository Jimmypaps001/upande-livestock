# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""How much of today's ration a herd has had, and what is left to mix.

The farm feeds in two runs a day, so a screen showing only "the day needs 5,106
kg" cannot tell an operator whether the morning has happened. This answers the
question the operator actually has: what is owed now.

It reads what was issued rather than what was planned. Every feeding posts a
Material Issue of the ration item through `_issue_feed`, so the day's issues
against this herd's ration item are what the animals actually got — including a
run someone entered by hand, and including a day that did not go to plan.

`suggested_portion` is a default, not a rule. It offers half the day when
nothing has gone out yet and the remainder afterwards, and it never goes below
zero. Nothing refuses a portion that makes the day add up differently: a herd
that ate more this morning is a fact to record, not an error.

Read-guarded on Herds.
"""

import frappe
from frappe.utils import flt, today

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding import _engine as feeding

# What the farm feeds in a day, so a fresh day offers a half rather than the lot.
RUNS_PER_DAY = 2


def _issued_today(item_code, herd):
	"""Ration units issued to this herd today, from the stock ledger.

	Matched on the ration item and the day, not on the Livestock Event: the
	event is written after the issue and a failure between the two would make
	the feed look un-issued when the store had already given it out.
	"""
	rows = frappe.db.sql(
		"""SELECT IFNULL(SUM(sed.qty), 0)
		   FROM `tabStock Entry Detail` sed
		   JOIN `tabStock Entry` se ON se.name = sed.parent
		   WHERE se.docstatus = 1
		     AND se.purpose = 'Material Issue'
		     AND sed.item_code = %(item)s
		     AND DATE(se.posting_date) = %(day)s
		     AND se.remarks LIKE %(herd)s""",
		{"item": item_code, "day": today(), "herd": f"%{herd}%"},
	)
	return flt(rows[0][0]) if rows else 0.0


@frappe.whitelist()
def feed_day_status(herd):
	def go():
		guard_read("Herds")
		herd_doc, bom, heads = feeding._herd_bom(herd)
		per_head = flt(bom.quantity) or 1.0
		day_qty = per_head * heads

		issued = _issued_today(bom.item, herd)
		remaining = max(day_qty - issued, 0.0)
		runs_done = 0 if not issued else round(issued / (day_qty / RUNS_PER_DAY)) if day_qty else 0

		if remaining <= 0:
			suggested = 0.0
		elif issued <= 0:
			suggested = 1.0 / RUNS_PER_DAY
		else:
			suggested = remaining / day_qty

		# What one ration unit weighs, so the screen can talk in kilograms —
		# a BOM unit is one animal's day, and its lines are the per-head kg.
		per_head_kg = sum(
			flt(r.qty)
			for r in frappe.get_all("BOM Item", filters={"parent": bom.name}, fields=["qty"])
		)
		return {
			"ok": True,
			"herd": herd,
			"heads": heads,
			"ration_item": bom.item,
			"runs_per_day": RUNS_PER_DAY,
			"day_qty": day_qty,
			"issued_today": issued,
			"remaining_today": remaining,
			"runs_done": runs_done,
			"suggested_portion": round(suggested, 4),
			"per_head_kg": per_head_kg,
			"day_kg": per_head_kg * heads,
			"issued_kg": per_head_kg * issued,
			"remaining_kg": per_head_kg * remaining,
			"complete": remaining <= 0,
		}

	return run(go, "livestock feed_day_status failed")
