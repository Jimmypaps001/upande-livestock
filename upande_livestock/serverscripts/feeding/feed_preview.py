"""What a herd's ration would cost and consume, without committing anything.

Read-only, and read-guarded on Herds: a preview still discloses herd size and
store balances."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding import _engine as feeding


@frappe.whitelist()
def feed_preview(herd):
	def go():
		guard_read("Herds")
		info = feeding.get_herd_feed_info(herd)
		info["ok"] = True
		return info

	return run(go, "livestock feed_preview failed")
