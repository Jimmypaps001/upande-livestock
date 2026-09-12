# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Open a case for an animal leaving the farm."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common import culling
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.culling.cull_evidence import cull_evidence


@frappe.whitelist()
def raise_cull(payload):
	"""Raise a departure, with the case for it frozen onto the record.

	The evidence is written down here and never recomputed. It is the argument
	that was made on the day, against the herd as it stood; a cow raised when
	she was bottom of the herd should not quietly stop being a candidate
	because two worse ones were bought in since.

	A PRODUCTIVE ANIMAL IS NOT REFUSED. She may be lame, or bad-tempered, or
	the farm may need her space. The record says in as many words that she was
	performing, which is what somebody reviewing it needs to see — a block here
	would only teach people to raise the case under a different flow.
	"""

	def go():
		guard("Livestock Disposal")
		d = as_dict(payload)
		animal = (d.get("animal") or "").strip()
		flow = culling.assert_flow((d.get("flow") or "").strip())

		if not animal:
			frappe.throw(_("Select the animal."))
		if frappe.db.get_value("Animal", animal, "disabled"):
			frappe.throw(_("{0} has already left the farm.").format(animal))

		open_case = frappe.db.exists("Livestock Disposal", {
			"animal": animal, "docstatus": 0,
			"custom_review_status": ["not in", [culling.REJECTED, culling.POSTED]],
		})
		if open_case:
			frappe.throw(
				_("There is already an open case for {0} ({1}). Settle that one first.")
				.format(animal, open_case)
			)

		if flow == culling.MORTALITY and not d.get("death_cause"):
			frappe.throw(_("Say what she died of. A death with no cause cannot be counted."))

		evidence = cull_evidence(animal=animal)
		if evidence.get("error"):
			frappe.throw(evidence["error"])

		doc = frappe.new_doc("Livestock Disposal")
		doc.animal = animal
		doc.animal_name = evidence["name"]
		doc.disposal_date = d.get("disposal_date") or today()
		doc.disposal_type = _disposal_type(flow, d.get("death_cause"))
		doc.custom_cull_flow = flow
		doc.custom_review_status = culling.FIRST_GATE[flow]
		doc.custom_evidence = evidence["case"]
		doc.custom_was_productive = 1 if evidence["was_productive"] else 0
		doc.custom_death_cause = d.get("death_cause") or None
		doc.book_value = flt(evidence.get("book_value"))
		doc.reason_details = d.get("reason") or None
		if flow == culling.SALE:
			doc.customer = d.get("customer") or None
			doc.buyer_name = d.get("buyer_name") or None
			doc.buyer_contact = d.get("buyer_contact") or None
			doc.sale_price = flt(d.get("sale_price"))
		if flow == culling.GIFT:
			doc.gifted_to = d.get("gifted_to") or None
			doc.gift_destination = d.get("gift_destination") or None
		doc.insert()

		return {
			"ok": True,
			"name": doc.name,
			"flow": flow,
			"status": doc.custom_review_status,
			"evidence": evidence["case"],
			"was_productive": bool(doc.custom_was_productive),
			"policy": evidence.get("policy"),
		}

	return run(go, "livestock raise_cull failed")


#: Which of the existing disposal types each flow and cause lands on. The types
#: pre-date this feature and STATUS_BY_DISPOSAL_TYPE in common/animal already
#: maps them onto the Animal's terminal status, so the flow chooses a type
#: rather than inventing a parallel vocabulary beside it.
_DEATH_TYPE = {
	"Disease — mastitis": "Died — Disease",
	"Disease — East Coast Fever": "Died — Disease",
	"Disease — other tick-borne": "Died — Disease",
	"Disease — other": "Died — Disease",
	"Injury / accident": "Died — Accident",
	"Predation": "Died — Accident",
	"Poisoning": "Died — Accident",
}


def _disposal_type(flow, cause):
	if flow == culling.SALE:
		return "Sold"
	if flow == culling.GIFT:
		return "Gifted"
	if flow == culling.DISPOSAL:
		return "Condemned"
	return _DEATH_TYPE.get(cause or "", "Died — Natural Causes")
