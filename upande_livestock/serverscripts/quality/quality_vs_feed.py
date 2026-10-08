# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Quality & Feed page: each milking herd's milk quality beside its ration."""

import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.quality._feed_quality import feed_quality


@frappe.whitelist()
def quality_vs_feed(payload=None):
	def go():
		guard_read("Milk Recording")
		return {"ok": True, **feed_quality(as_dict(payload).get("days") or 90)}

	return run(go, "livestock quality_vs_feed failed")
