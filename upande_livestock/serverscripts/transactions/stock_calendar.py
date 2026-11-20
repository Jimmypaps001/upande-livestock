# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Transactions calendar: which days have livestock drafts, which only posted entries."""

import frappe
from frappe import _
from frappe.utils import getdate

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read_or_livestock, run
from upande_livestock.serverscripts.transactions._drafts import day_counts


@frappe.whitelist()
def stock_calendar(payload=None):
	def go():
		# The farm roles carry no ERPNext Stock Entry permission, and should not need
		# it to see the livestock entries (and only those) that this page lists.
		guard_read_or_livestock("Stock Entry")
		d = as_dict(payload)
		if not d.get("from_date") or not d.get("to_date"):
			frappe.throw(_("Say which days to show."))
		start, end = getdate(d["from_date"]), getdate(d["to_date"])
		if (end - start).days > 62:
			frappe.throw(_("Ask for at most two months at a time."))
		return {"ok": True, "days": day_counts(start, end)}

	return run(go, "livestock stock_calendar failed")
