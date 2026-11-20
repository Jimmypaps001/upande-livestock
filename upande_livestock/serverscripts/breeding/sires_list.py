"""Every Livestock Sire, active or not, for the Sires page."""

import frappe

from upande_livestock.serverscripts.common import livestock_sire as LS
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def sires_list(payload=None):
	def go():
		guard_read("Livestock Sire")
		rows = frappe.get_all(
			"Livestock Sire",
			fields=["name", "sire_name", "sire_code", "sire_type", "semen_item", "animal", "sexed", "active", "breed", "supplier"],
			order_by="sire_name asc", limit_page_length=2000,
		)
		names = {r.name: r.item_name for r in frappe.get_all(
			"Item", filters={"name": ["in", [r.semen_item for r in rows if r.semen_item] or [""]]},
			fields=["name", "item_name"])}
		return {"ok": True, "sires": [
			{"name": r.name, "sire_name": r.sire_name, "code": r.sire_code or "",
			 "label": LS.label(r.sire_name, r.sire_code), "sire_type": r.sire_type,
			 "semen_item": r.semen_item or "", "semen_item_name": names.get(r.semen_item) or r.semen_item or "", "animal": r.animal or "", "breed": r.breed or "", "supplier": r.supplier or "",
			 "sexed": 1 if r.sexed else 0, "active": 1 if r.active else 0} for r in rows]}

	return run(go, "livestock sires_list failed")
