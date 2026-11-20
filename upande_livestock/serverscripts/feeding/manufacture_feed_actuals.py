# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""manufacture_feed_actuals: split out of feeding.feed_actuals; that module still re-exports it, so the old dotted path resolves."""

from frappe import _
import frappe

from upande_livestock.serverscripts.common.employee import acting_employee
from upande_livestock.serverscripts.common import event_types
from upande_livestock.serverscripts.feeding import _feed_types as feed_types
from upande_livestock.serverscripts.common.envelope import guard_stock, run
from upande_livestock.serverscripts.common.idempotency import idempotent


@frappe.whitelist()
@idempotent
def manufacture_feed_actuals(herd, date=None, employee=None, allow_shortage=False):
	"""Mix and issue the day's actuals. Short stock leaves a dated draft.

	`employee` is honoured only for a System Manager or Administrator; anyone
	else is always recorded as their own linked Employee.

	Returns `{ok, ...herd_day, pending, waiting_for, engine}`.
	"""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.feeding.feed_actuals import manufacture_day


	def go():
		event_types.assert_enabled("Feeding")
		feed_types.assert_on(feed_types.DAY_SHEET)
		guard_stock("Work Order", "Stock Entry")
		# The operator the desk picked (System Manager only), else the user's own.
		who = acting_employee(employee)
		if not who:
			frappe.throw(
				_("No Employee is linked to your user ({0}). Choose who is feeding, or ask HR to link your user to an Employee.").format(
					frappe.session.user
				)
			)
		out = manufacture_day(herd, date, who, allow_shortage=frappe.parse_json(allow_shortage))
		out["ok"] = True
		return out

	return run(go, "livestock manufacture_feed_actuals failed")
