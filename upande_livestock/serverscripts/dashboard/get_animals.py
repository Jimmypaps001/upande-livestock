"""The dashboard's animal table.

Read-guarded on Animal."""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.choices import is_active
from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.dashboard._shared import _herd_labels


@frappe.whitelist()
def get_animals() -> dict:
	"""Animals tab: a capped, searchable/filterable list plus summary
	counts and the option lists the client uses to build its filters."""
	guard_read("Animal")
	try:
		herds = _herd_labels()
		rows = frappe.get_all(
			"Animal",
			fields=[
				"name",
				"tag_number",
				"burn_name",
				"sex",
				"species",
				"breed",
				"current_herd",
				"status",
				"repro_status",
				"days_in_milk",
				"parity",
				"disabled",
			],
			order_by="tag_number asc",
			limit_page_length=1000,
		)
		for r in rows:
			r["herd_label"] = herds.get(r.get("current_herd") or "", r.get("current_herd") or "")
		active = [r for r in rows if is_active(r)]
		summary = {
			"total": len(rows),
			"active": len(active),
			"milking": sum(1 for r in rows if flt(r.get("days_in_milk")) > 0),
			"pregnant": sum(1 for r in rows if "pregn" in (r.get("repro_status") or "").lower()),
		}
		return {
			"rows": rows,
			"summary": summary,
			"capped": len(rows) >= 1000,
			"filters": {
				"herds": sorted({r["herd_label"] for r in rows if r.get("herd_label")}),
				"statuses": sorted({r["status"] for r in rows if r.get("status")}),
				"species": sorted({r["species"] for r in rows if r.get("species")}),
			},
		}
	except Exception:
		frappe.log_error(title="livestock get_animals failed")
		return {"rows": [], "summary": {}, "filters": {}, "error": "Could not load animals."}
