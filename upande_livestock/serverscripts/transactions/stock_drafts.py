# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Transactions page: livestock stock issues still in draft."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.transactions._drafts import draft_rows


@frappe.whitelist()
def stock_drafts():
	def go():
		guard_read("Stock Entry")
		return {"ok": True, "drafts": draft_rows()}

	return run(go, "livestock stock_drafts failed")
