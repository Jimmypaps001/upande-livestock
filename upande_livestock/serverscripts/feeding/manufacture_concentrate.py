"""Manufacture a concentrate so a TMR run can consume it.

Same Work Order route as the TMR, and the same two guards."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard, run
from upande_livestock.serverscripts.feeding import _engine as feeding


@frappe.whitelist()
def manufacture_concentrate(
	item_code, qty=None, bom_no=None, allow_shortage=False,
	source_warehouse=None, target_warehouse=None,
):
	def go():
		guard("Work Order")
		guard("Stock Entry")
		res = feeding.manufacture_concentrate(
			item_code, qty=qty, bom_no=bom_no, allow_shortage=allow_shortage,
			source_warehouse=source_warehouse, target_warehouse=target_warehouse,
		)
		res["ok"] = True
		return res

	return run(go, "livestock manufacture_concentrate failed")
