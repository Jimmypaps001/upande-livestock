"""The alerts still open, for whoever is looking at the herd.

Read-guarded on Livestock Alert. Split out from the scheduler that raises them:
one is a REST surface, the other a nightly job, and naming one file for both
would have hidden the scheduler behind an endpoint's name.
"""

import frappe

from upande_livestock.serverscripts.alerts._shared import KINDS
from upande_livestock.serverscripts.common.envelope import guard_read


@frappe.whitelist()
def open_alerts(kind=None, limit=200):
	"""Alerts nobody has actioned yet, newest first."""
	guard_read("Livestock Alert")
	filters = {"status": "Open"}
	if kind:
		filters["alert_kind"] = kind
	rows = frappe.get_all(
		"Livestock Alert",
		filters=filters,
		fields=["name", "alert_kind", "alert_date", "animal", "herd", "severity", "message"],
		order_by="severity asc, alert_date asc",
		limit=int(limit),
	)
	return {
		"ok": True,
		"alerts": rows,
		"counts": {k: sum(1 for r in rows if r.alert_kind == k) for k in KINDS},
	}
