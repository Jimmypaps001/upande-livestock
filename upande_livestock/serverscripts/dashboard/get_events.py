"""The dashboard's event feed.

Read-guarded on Animal."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.dashboard._shared import _herd_labels


@frappe.whitelist()
def get_events() -> dict:
	"""Events tab: recent Livestock Events + counts by type."""
	guard_read("Animal")
	try:
		herds = _herd_labels()
		rows = frappe.get_all(
			"Livestock Event",
			fields=[
				"name",
				"animal",
				"current_herd",
				"new_herd",
				"event_type",
				"event_date",
				"service_type",
				"service_status",
				"pregnancy_confirmation_status",
				"diagnosis_result",
			],
			order_by="event_date desc, creation desc",
			limit_page_length=300,
		)
		counts: dict = {}
		for r in rows:
			r["herd_label"] = herds.get(r.get("current_herd") or "", r.get("current_herd") or "")
			r["event_date"] = str(r["event_date"]) if r.get("event_date") else ""
			t = r.get("event_type") or "Other"
			counts[t] = counts.get(t, 0) + 1
		return {
			"rows": rows,
			"summary": {"total": len(rows), "by_type": counts},
			"filters": {"types": sorted({r["event_type"] for r in rows if r.get("event_type")})},
		}
	except Exception:
		frappe.log_error(title="livestock get_events failed")
		return {"rows": [], "summary": {}, "filters": {}, "error": "Could not load events."}
