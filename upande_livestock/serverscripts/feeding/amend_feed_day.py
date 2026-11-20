# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""amend_feed_day: split out of feeding.feed_actuals; that module still re-exports it, so the old dotted path resolves."""

import frappe

from upande_livestock.serverscripts.feeding import _feed_types as feed_types
from upande_livestock.serverscripts.common.envelope import guard, run
from upande_livestock.serverscripts.common.idempotency import idempotent


@frappe.whitelist()
@idempotent
def amend_feed_day(herd, date, components, remarks=None):
	"""Amend what a herd was actually fed. `components`: `[{item_code, actual_kg}]`;
	an actual of 0 removes an item that was not used.

	Returns `{ok, ...herd_day}`. The herd's recipe is never changed and the
	amendment applies to this herd and day only.
	"""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.feeding.feed_actuals import DOCTYPE, amend_day


	def go():
		feed_types.assert_on(feed_types.DAY_SHEET)
		guard(DOCTYPE)
		out = amend_day(herd, date, components, remarks)
		out["ok"] = True
		return out

	return run(go, "livestock amend_feed_day failed")
