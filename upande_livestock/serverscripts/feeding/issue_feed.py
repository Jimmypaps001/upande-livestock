"""Issue manufactured feed from the store to a herd.

Guards Stock Entry: this moves real stock."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard, run
from upande_livestock.serverscripts.feeding import _engine as feeding


@frappe.whitelist()
def issue_feed(herd, qty, employee=None):
	def go():
		guard("Stock Entry")
		res = feeding.feed_herd(herd, qty, employee=employee)
		res["ok"] = True
		return res

	return run(go, "livestock issue_feed failed")
