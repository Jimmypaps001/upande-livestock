# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Transactions page: livestock stock issues still in draft."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read_or_livestock, run
from upande_livestock.serverscripts.transactions._drafts import draft_rows


@frappe.whitelist()
def stock_drafts():
	def go():
		# The farm roles carry no ERPNext Stock Entry permission, and should not need
		# it to see the livestock entries (and only those) that this page lists.
		guard_read_or_livestock("Stock Entry")
		return {"ok": True, "drafts": draft_rows()}

	return run(go, "livestock stock_drafts failed")
