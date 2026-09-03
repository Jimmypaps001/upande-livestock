"""The Overview dashboard's single payload: KPIs, the 30-day milk chart,
top herds and herd tiles.

One call on load, so the block renders from one response. Every read is
defensive — thin data degrades to zeros rather than an error. Read-guarded on
Animal, which it had no check for at all."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.dashboard._shared import _build, _zeros


@frappe.whitelist()
def get_livestock_workspace_stats() -> dict:
	guard_read("Animal")
	try:
		return _build()
	except Exception:
		frappe.log_error(title="livestock workspace stats failed")
		out = _zeros()
		out["error"] = "Could not load livestock stats."
		return out
