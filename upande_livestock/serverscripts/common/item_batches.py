# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which batch an event's items would come out of.

The same question the Feeding page asks, asked by an event form. It is
deliberately the same rule and the same code — `suggest_batches` already
decides first-expiry-first-out, reports what the store cannot cover, and names
the disabled batch holding stock nobody can issue. Two implementations of that
would be two answers about one store.

`feed_batches` is the feeding-shaped door onto it; this is the event-shaped one.
Read-only, so a form may ask again whenever a store or a quantity changes.
"""

import frappe

from upande_livestock.serverscripts.common.batches import suggest_batches
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def event_batches(lines):
	"""``[{item_code, qty, warehouse}]`` in, a proposal per line out."""

	def go():
		guard_read("Item")
		return {"ok": True, "lines": suggest_batches(frappe.parse_json(lines) or [])}

	return run(go, "livestock event_batches failed")
