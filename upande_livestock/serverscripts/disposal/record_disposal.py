"""Dispose of an animal — sale, death or cull — retiring it and its asset."""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common.envelope import as_dict, guard, guard_read, run
from upande_livestock.serverscripts.common.vet import resolve_vet
from upande_livestock.serverscripts.common.withdrawal import withdrawal_warning


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
		disposal_date, is_backdated = backdate.resolve(d, "disposal_date")
		backdate.assert_allowed(is_backdated)
		doc.disposal_date = disposal_date
		backdate.stamp(doc, is_backdated)
		doc.disposal_type = d.get("disposal_type")
		if doc.disposal_type == "Sold":
			# Live cattle sell by the kilogram: the amount is worked out from the
			# exit weight (the latest weighing when none is given) and the price.
			if flt(d.get("price_per_kg")) <= 0:
				frappe.throw(_("Enter the price per kg the animal was sold at."))
			doc.price_per_kg = flt(d.get("price_per_kg"))
		else:
			doc.sale_price = flt(d.get("sale_price")) or None
		doc.exit_weight_kg = flt(d.get("exit_weight_kg")) or None
		doc.customer = d.get("customer") or None
		doc.buyer_name = d.get("buyer_name")
		doc.buyer_contact = d.get("buyer_contact")
		doc.gifted_to = d.get("gifted_to")
		doc.gift_destination = d.get("gift_destination")
		doc.reason_details = d.get("reason_details")
		doc.witness = d.get("witness")
		doc.vet = resolve_vet(d)
		doc.insert()
		doc.submit()
		warnings = list(doc.flags.get("warnings") or [])
		doc.reload()
		status, disabled = frappe.db.get_value("Animal", doc.animal, ["status", "disabled"])
		return {
			"ok": True,
			"name": doc.name,
			"animal_status": status,
			"animal_disabled": int(disabled or 0),
			"exit_weight_kg": doc.exit_weight_kg,
			"sale_price": doc.sale_price,
			"final_adg_kg": doc.final_adg_kg,
			# Warned, not blocked: the farm decides, but it is told.
			"warnings": warnings,
		}

	return run(go, "livestock record_disposal failed")


@frappe.whitelist()
def disposal_warning(animal, disposal_date=None):
	"""The withdrawal warning the desk form shows before an exit is saved."""
	guard_read("Livestock Disposal")
	return withdrawal_warning(animal, disposal_date or frappe.utils.today())
