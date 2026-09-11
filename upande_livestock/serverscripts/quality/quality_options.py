# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the Quality page needs to draw itself: the farm's rules, and the
recordings still waiting on a lab figure."""

import frappe
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.common import quality
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def quality_options(days=60):
	"""The capture mode, the thresholds, and what is outstanding.

	Outstanding is read off the stamped flag rather than recomputed from the
	lab columns, so a recording taken before the farm turned the requirement on
	is not retrospectively called late.
	"""

	def go():
		guard_read("Milk Recording")
		since = add_days(today(), -int(flt(days) or 60))

		pending = frappe.get_all(
			"Milk Recording",
			filters={
				"docstatus": 1,
				"custom_quality_pending": 1,
				"recording_date": [">=", since],
			},
			fields=[
				"name", "herd", "recording_date", "milking_time",
				"total_yield_kg", "net_yield_kg", "cows_milked",
			],
			order_by="recording_date desc, milking_time desc",
			limit_page_length=200,
		)

		ceiling = quality.scc_ceiling()
		recent = frappe.get_all(
			"Milk Recording",
			filters={
				"docstatus": 1,
				"custom_quality_pending": 0,
				"recording_date": [">=", since],
			},
			fields=[
				"name", "herd", "recording_date", "bulk_scc",
				"fat_percent", "protein_percent", "lab_test_date",
			],
			order_by="recording_date desc",
			limit_page_length=200,
		)
		for r in recent:
			r["over_ceiling"] = bool(ceiling and flt(r.get("bulk_scc")) > ceiling)

		return {
			"ok": True,
			"mode": quality.capture_mode(),
			"required_at_milking": quality.required_at_milking(),
			"required_in_lab": quality.required_in_lab(),
			"scc_ceiling": ceiling,
			"pending": pending,
			"recent": recent,
			"can_write": bool(frappe.has_permission("Milk Recording", "write")),
		}

	return run(go, "livestock quality_options failed")
