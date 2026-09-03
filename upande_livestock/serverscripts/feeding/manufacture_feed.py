"""Manufacture a herd's TMR through a Work Order.

Guards Work Order and Stock Entry because that is what it creates — asked
against the target DocType rather than a role, so renaming or re-scoping a role
cannot silently open it."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard, run
from upande_livestock.serverscripts.feeding import _engine as feeding


@frappe.whitelist()
def manufacture_feed(herd, allow_shortage=False, employee=None):
	def go():
		guard("Work Order")
		guard("Stock Entry")
		res = feeding.manufacture_herd_feed(herd, allow_shortage=allow_shortage, employee=employee)
		res["ok"] = True
		return res

	return run(go, "livestock manufacture_feed failed")
