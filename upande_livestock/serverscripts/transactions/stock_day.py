# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One day's livestock stock entries, drafts and posted, for the Transactions list."""

import frappe
from frappe import _
from frappe.utils import getdate

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read_or_livestock, run
from upande_livestock.serverscripts.transactions._drafts import entry_rows


@frappe.whitelist()
def stock_day(payload=None):
	def go():
		# The farm roles carry no ERPNext Stock Entry permission, and should not need
		# it to see the livestock entries (and only those) that this page lists.
		guard_read_or_livestock("Stock Entry")
		day = as_dict(payload).get("date")
		if not day:
			frappe.throw(_("Say which day to show."))
		return {"ok": True, "date": str(getdate(day)), "entries": entry_rows("AND se.posting_date = %(day)s", {"day": getdate(day)})}

	return run(go, "livestock stock_day failed")
