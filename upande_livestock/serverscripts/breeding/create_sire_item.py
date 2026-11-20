"""Make a sire's straw Item when the store has none. Livestock Manager only."""

import frappe

from upande_livestock.serverscripts.breeding.save_sire import _assert_manager
from upande_livestock.serverscripts.common.envelope import as_dict, run
from upande_livestock.serverscripts.common.sire_items import make_item


@frappe.whitelist()
def create_sire_item(payload=None):
	def go():
		_assert_manager()
		d = as_dict(payload)
		return {"ok": True, "item": make_item(d.get("sire_name"), d.get("sire_code"))}

	return run(go, "livestock create_sire_item failed")
