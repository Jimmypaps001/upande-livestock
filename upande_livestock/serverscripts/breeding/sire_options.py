"""The bulls a Service form can pick, each with its code."""

import frappe

from upande_livestock.serverscripts.common import livestock_sire as LS
from upande_livestock.serverscripts.common.envelope import guard_read, run


def options(type=None, q=None):
	"""[{name, code, label, type, semen_item}] of the active sires, by name."""
	filters = {"active": 1}
	if type:
		filters["sire_type"] = type
	q = (q or "").strip()
	or_filters = ([["sire_name", "like", f"%{q}%"], ["sire_code", "like", f"%{q}%"]] if q else None)
	rows = frappe.get_all(
		"Livestock Sire", filters=filters, or_filters=or_filters,
		fields=["name", "sire_name", "sire_code", "sire_type", "semen_item"],
		order_by="sire_name asc", limit_page_length=500,
	)
	return [{"name": r.name, "sire_name": r.sire_name, "code": r.sire_code or "",
	         "label": LS.label(r.sire_name, r.sire_code), "type": r.sire_type,
	         "semen_item": r.semen_item or ""} for r in rows]


@frappe.whitelist()
def sire_options(type=None, q=None):
	def go():
		guard_read("Livestock Sire")
		return {"ok": True, "sires": options(type, q)}

	return run(go, "livestock sire_options failed")
