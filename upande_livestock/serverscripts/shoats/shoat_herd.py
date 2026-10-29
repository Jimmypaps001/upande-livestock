# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One shoat herd: the card, the latest ledger lines, weight samples, matings and treatments."""

import frappe
from frappe import _
from frappe.utils import today

from upande_livestock.serverscripts.common import shoats
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def shoat_herd(herd=None):
	def go():
		guard_read("Herds")
		if not herd or not shoats.is_by_number(herd):
			frappe.throw(_("{0} is not a shoat herd.").format(herd or ""))
		return {
			"ok": True, "today": today(), "herd": shoats.herd_row(herd),
			"ledger": shoats.ledger(herd, limit=15), "weights": shoats.sample_rows(herd),
			"matings": shoats.matings(herd), "treatments": shoats.treatment_rows(herd), "warnings": [],
		}

	return run(go, "livestock shoat_herd failed")
