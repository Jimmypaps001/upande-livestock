# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One day's livestock stock entries, drafts and posted, for the Transactions list."""

import frappe
from frappe import _
from frappe.utils import getdate

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.transactions._drafts import entry_rows


@frappe.whitelist()
def stock_day(payload=None):
	def go():
		guard_read("Stock Entry")
		day = as_dict(payload).get("date")
		if not day:
			frappe.throw(_("Say which day to show."))
		return {"ok": True, "date": str(getdate(day)), "entries": entry_rows("AND se.posting_date = %(day)s", {"day": getdate(day)})}

	return run(go, "livestock stock_day failed")
