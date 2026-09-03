"""Manufacture a herd's TMR through a Work Order.

Guards Work Order and Stock Entry because that is what it creates — asked
against the target DocType rather than a role, so renaming or re-scoping a role
cannot silently open it.

`portion` records a farm that feeds twice a day: 0.5 mixes and issues half the
day's ration. Nothing here enforces two halves — `feed_day_status` is what tells
the screen how much of the day is left, and a day that does not add up is a real
day, not an error."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard, run
from upande_livestock.serverscripts.feeding import _engine as feeding


@frappe.whitelist()
def manufacture_feed(herd, allow_shortage=False, employee=None, portion=1.0):
	def go():
		guard("Work Order")
		guard("Stock Entry")
		res = feeding.manufacture_herd_feed(
			herd, allow_shortage=allow_shortage, employee=employee, portion=portion
		)
		res["ok"] = True
		return res

	return run(go, "livestock manufacture_feed failed")
