# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""cover_policies: split out of animals.animal_cover; that module still re-exports it, so the old dotted path resolves."""

import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.common import asset_cover


@frappe.whitelist()
def cover_policies(payload=None):
	"""The running policies she could be added to."""

	def go():
		guard_read("Animal")
		d = as_dict(payload)
		company = frappe.db.get_value("Animal", d["animal"], "company") if d.get("animal") else None
		return {"ok": True, "available": asset_cover.available(),
		        "policies": asset_cover.open_policies(company)}

	return run(go, "livestock cover_policies failed")
