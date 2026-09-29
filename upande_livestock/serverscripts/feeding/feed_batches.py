# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What batches a feed run would take, before it takes them.

Spray has a storesman standing at a draft, so it can propose batches and wait.
Feeding does not — `_run_manufacture` builds the transfer and submits it in one
call, because mixed feed is eaten long before anyone would count it. That is
why `common/batches` decides by rule rather than asking.

It still has to be VISIBLE. A rule nobody can see is a rule nobody can correct,
and the correction matters here: batch DAIR-2026-00037 sat at net -32,381 in
the concentrate store across 67 issues and no receipts, and every feed run that
touched it read as normal on the way past. This endpoint is the look before the
run: what the rule would take, from which batch, out of which store, and what
the store cannot cover.

Read-only. Nothing here writes, so the page may ask again every time the
operator changes a store or a tonnage.

Read-guarded on Item, like the rest of the stock-disclosing endpoints.
"""

import frappe

from upande_livestock.serverscripts.common.batches import suggest_batches
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def feed_batches(lines):
	"""``[{item_code, qty, warehouse}]`` in, a proposal per line out."""

	def go():
		guard_read("Item")
		return {"ok": True, "lines": suggest_batches(frappe.parse_json(lines) or [])}

	return run(go, "livestock feed_batches failed")
