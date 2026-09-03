"""The dashboard's health table: open cases and recent treatments.

Read-guarded on Animal."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.dashboard._shared import _OPEN_CASE_STATUS, _herd_labels


@frappe.whitelist()
def get_health() -> dict:
	"""Health tab: Livestock Health Cases (open first) + summary counts."""
	guard_read("Animal")
	try:
		herds = _herd_labels()
		rows = frappe.get_all(
			"Livestock Health Case",
			fields=[
				"name",
				"animal",
				"animal_name",
				"current_herd",
				"opened_date",
				"case_status",
				"severity",
				"provisional_diagnosis",
				"confirmed_diagnosis",
				"vet_called",
				"is_zoonotic",
				"is_notifiable",
			],
			order_by="opened_date desc",
			limit_page_length=300,
		)
		# Stable sort keeps date order within the open / closed groups.
		rows.sort(key=lambda r: 0 if r.get("case_status") in _OPEN_CASE_STATUS else 1)
		for r in rows:
			r["herd_label"] = herds.get(r.get("current_herd") or "", r.get("current_herd") or "")
			r["opened_date"] = str(r["opened_date"]) if r.get("opened_date") else ""
			r["diagnosis"] = r.get("confirmed_diagnosis") or r.get("provisional_diagnosis") or ""
		summary = {
			"total": len(rows),
			"open": sum(1 for r in rows if r.get("case_status") in _OPEN_CASE_STATUS),
			"recovered": sum(1 for r in rows if r.get("case_status") == "Recovered"),
			"zoonotic": sum(1 for r in rows if r.get("is_zoonotic")),
			"notifiable": sum(1 for r in rows if r.get("is_notifiable")),
		}
		return {
			"rows": rows,
			"summary": summary,
			"filters": {
				"statuses": sorted({r["case_status"] for r in rows if r.get("case_status")}),
				"severities": sorted({r["severity"] for r in rows if r.get("severity")}),
			},
		}
	except Exception:
		frappe.log_error(title="livestock get_health failed")
		return {"rows": [], "summary": {}, "filters": {}, "error": "Could not load health cases."}
