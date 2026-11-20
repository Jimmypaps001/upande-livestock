# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""reset_feed_day: split out of feeding.feed_actuals; that module still re-exports it, so the old dotted path resolves."""

import frappe

from upande_livestock.serverscripts.feeding import _feed_types as feed_types
from upande_livestock.serverscripts.common.envelope import guard, run
from upande_livestock.serverscripts.common.idempotency import idempotent


@frappe.whitelist()
@idempotent
def reset_feed_day(herd, date):
	"""Put a herd's day back to the recipe (drops the amendment). Refused once mixed.

	Returns `{ok, ...herd_day}`.
	"""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.feeding.feed_actuals import DOCTYPE, reset_day


	def go():
		feed_types.assert_on(feed_types.DAY_SHEET)
		guard(DOCTYPE)
		out = reset_day(herd, date)
		out["ok"] = True
		return out

	return run(go, "livestock reset_feed_day failed")
