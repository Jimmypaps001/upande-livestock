"""The straw Items a sire can be linked to, for the Sires modal."""

import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.common.sire_items import candidates


@frappe.whitelist()
def sire_items(payload=None):
	def go():
		guard_read("Livestock Sire")
		d = as_dict(payload)
		return {"ok": True, **candidates(d.get("q"), d.get("sire_name"), d.get("sire_code"), d.get("current"))}

	return run(go, "livestock sire_items failed")
