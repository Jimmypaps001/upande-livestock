"""Move a herd's mixed ration from the mixing store to its paddock or pen.

Guards Stock Entry: this moves real stock. A feeding run does the same step on its own for a herd
with a paddock; this is for feed mixed ahead of time."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_stock, run
from upande_livestock.serverscripts.feeding import _engine as feeding


@frappe.whitelist()
def move_feed_to_paddock(herd, qty, source_warehouse=None, posting_date=None):
	def go():
		guard_stock("Stock Entry")
		res = feeding.move_ration_to_paddock(herd, qty, source_warehouse=source_warehouse, posting_date=posting_date)
		res["ok"] = True
		return res

	return run(go, "livestock move_feed_to_paddock failed")
