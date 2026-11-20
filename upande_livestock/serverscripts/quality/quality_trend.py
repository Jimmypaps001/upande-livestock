# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Milk quality over time, batch by batch, for the Milking dashboard chart."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.milking.milk_by_herd import window

FIELDS = [
	"name", "sample_date", "shift", "butterfat_percent", "protein_percent", "snf_percent",
	"ph", "tta", "freezing_point", "aflatoxin_ppt", "overall_result",
]


def build(rows):
	"""One point per test; a figure the lab did not take is None, not 0."""
	out = []
	for r in rows:
		pt = {"name": r["name"], "date": str(r["sample_date"]), "shift": r.get("shift"),
		      "result": r.get("overall_result") or "Not assessed"}
		for key, field in (("fat", "butterfat_percent"), ("protein", "protein_percent"),
		                   ("snf", "snf_percent"), ("ph", "ph"), ("tta", "tta"),
		                   ("freezing_point", "freezing_point"), ("aflatoxin", "aflatoxin_ppt")):
			v = r.get(field)
			pt[key] = float(v) if v else None
		out.append(pt)
	return out


@frappe.whitelist()
def quality_trend(from_date=None, to_date=None):
	def go():
		guard_read("Milk Quality Test")
		start, end = window(from_date, to_date)
		rows = frappe.get_all(
			"Milk Quality Test",
			filters={"sample_date": ["between", [start, end]]},
			fields=FIELDS,
			order_by="sample_date asc, creation asc",
			limit_page_length=0,
		)
		return {"ok": True, "tests": build(rows)}

	return run(go, "livestock quality_trend failed")
