"""Dispose of an animal — sale, death or cull — retiring it and its asset."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


@frappe.whitelist()
def record_disposal(payload):
	"""Retire an animal by creating and submitting a Livestock Disposal.

	All the consequences live in LivestockDisposal.on_submit(): it posts the asset
	sale or scrap through api/assets.py and calls retire_animal(), which sets the
	final status, sets `disabled`, and recomputes the herd headcount. This endpoint
	deliberately adds none of that itself — one submit is the whole flow.
	"""

	def go():
		guard("Livestock Disposal")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("disposal_type"):
			frappe.throw(_("Select how the animal left the herd."))
		doc = frappe.new_doc("Livestock Disposal")
		doc.animal = d.get("animal")
		doc.disposal_date = d.get("disposal_date") or today()
		doc.disposal_type = d.get("disposal_type")
		doc.sale_price = flt(d.get("sale_price")) or None
		doc.customer = d.get("customer") or None
		doc.buyer_name = d.get("buyer_name")
		doc.buyer_contact = d.get("buyer_contact")
		doc.gifted_to = d.get("gifted_to")
		doc.gift_destination = d.get("gift_destination")
		doc.reason_details = d.get("reason_details")
		doc.witness = d.get("witness")
		doc.insert()
		doc.submit()
		doc.reload()
		status, disabled = frappe.db.get_value("Animal", doc.animal, ["status", "disabled"])
		return {
			"ok": True,
			"name": doc.name,
			"animal_status": status,
			"animal_disabled": int(disabled or 0),
		}

	return run(go, "livestock record_disposal failed")
