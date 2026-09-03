"""The dashboard's milk-production table.

Read-guarded on Animal."""

import frappe
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.dashboard._shared import _herd_labels


@frappe.whitelist()
def get_production() -> dict:
	"""Production tab: recent Milk Recordings + 30-day quality/volume summary."""
	guard_read("Animal")
	try:
		herds = _herd_labels()
		rows = frappe.get_all(
			"Milk Recording",
			fields=[
				"name",
				"recording_date",
				"session",
				"herd",
				"cows_milked",
				"total_yield_kg",
				"discarded_kg",
				"net_yield_kg",
				"discard_reason",
				"protein_percent",
				"bulk_scc",
				"milk_revenue",
			],
			order_by="recording_date desc, creation desc",
			limit_page_length=200,
		)
		for r in rows:
			r["herd_label"] = herds.get(r.get("herd") or "", r.get("herd") or "")
			r["recording_date"] = str(r["recording_date"]) if r.get("recording_date") else ""

		since = str(add_days(today(), -30))
		recent = [r for r in rows if r["recording_date"] and r["recording_date"] >= since]

		def _avg(key):
			vals = [flt(r.get(key)) for r in recent if r.get(key)]
			return round(sum(vals) / len(vals), 2) if vals else 0

		summary = {
			"records": len(recent),
			"net_kg": round(sum(flt(r.get("net_yield_kg")) for r in recent), 1),
			"revenue": round(sum(flt(r.get("milk_revenue")) for r in recent), 2),
			# Fat is no longer recorded at milking, so there is nothing to average.
			# The discarded litres and why they went are what the summary can act on.
			"discarded_kg": round(sum(flt(r.get("discarded_kg")) for r in recent), 1),
			"avg_protein": _avg("protein_percent"),
			"avg_scc": _avg("bulk_scc"),
		}
		return {
			"rows": rows,
			"summary": summary,
			"filters": {
				"herds": sorted({r["herd_label"] for r in rows if r.get("herd_label")}),
				"sessions": sorted({r["session"] for r in rows if r.get("session")}),
			},
		}
	except Exception:
		frappe.log_error(title="livestock get_production failed")
		return {"rows": [], "summary": {}, "filters": {}, "error": "Could not load production."}
