# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Insurance cover of one animal, through Upande Asset (see common/asset_cover)."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import asset_cover
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run


def _animal(d):
	name = (d.get("animal") or "").strip()
	if not name:
		frappe.throw(_("Select an animal."))
	if not frappe.db.exists("Animal", name):
		frappe.throw(_("{0} is not an animal on this farm.").format(name))
	return name


@frappe.whitelist()
def animal_cover(payload=None):
	"""Is she insured, by which policy, until when."""

	def go():
		guard_read("Animal")
		return {"ok": True, **asset_cover.cover_for_animal(_animal(as_dict(payload)))}

	return run(go, "livestock animal_cover failed")


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


@frappe.whitelist()
def insure_animal(payload):
	"""Put her Asset under a policy. Upande Asset decides who may."""

	def go():
		guard_read("Animal")
		d = as_dict(payload)
		res = asset_cover.put_under_cover(
			_animal(d), d.get("policy"), d.get("sum_insured"),
			d.get("effective_date"), d.get("endorsement_no"))
		return {"ok": True, **res}

	return run(go, "livestock insure_animal failed")
