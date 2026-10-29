# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A shoat herd's ledger, newest first, paged, optionally one event type."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import shoats
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def shoat_ledger(herd=None, event_type=None, limit=50, start=0):
	def go():
		guard_read("Herd Count Event")
		if not herd or not shoats.is_by_number(herd):
			frappe.throw(_("{0} is not a shoat herd.").format(herd or ""))
		rows = shoats.ledger(herd, event_type=event_type or None, limit=min(int(limit or 50), 500), start=int(start or 0))
		return {"ok": True, "herd": herd, "head": shoats.head(herd), "rows": rows, "warnings": []}

	return run(go, "livestock shoat_ledger failed")
