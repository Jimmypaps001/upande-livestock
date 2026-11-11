"""Issue manufactured feed from the store to a herd.

Guards Stock Entry: this moves real stock."""

import frappe

from upande_livestock.serverscripts.common import event_types
from upande_livestock.serverscripts.common.envelope import guard_stock, run
from upande_livestock.serverscripts.feeding import _engine as feeding


@frappe.whitelist()
def issue_feed(herd, qty, employee=None, posting_date=None, source_warehouse=None):
	def go():
		# A farm that switched Feeding off (Settings → Events) is refused in
		# words before any stock moves — not left to the Feeding event failing
		# after the feed has already left the store.
		event_types.assert_enabled("Feeding")
		guard_stock("Stock Entry")
		res = feeding.feed_herd(
			herd, qty, employee=employee, posting_date=posting_date,
			source_warehouse=source_warehouse,
		)
		res["ok"] = True
		return res

	return run(go, "livestock issue_feed failed")
