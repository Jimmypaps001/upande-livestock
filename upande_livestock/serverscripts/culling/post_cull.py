# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Post an approved cull: move her out, retire her, settle the asset."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import culling
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event


@frappe.whitelist()
def post_cull(payload):
	"""Execute the departure. This is the irreversible step.

	Order matters, and it is: MOVE HER FIRST, THEN SUBMIT. The move is a
	Livestock Event whose processor refuses a herd change on an animal that is
	no longer active, and submitting the Disposal is what retires her. Posting
	first would leave her disabled inside Lactating 1, which is exactly the
	state the holding herd exists to prevent.

	The Disposal's own on_submit does the asset posting and the retirement; none
	of that is repeated here. What this adds is the move, the status, and — for
	a death on an insured animal — the claim.
	"""

	def go():
		guard("Livestock Disposal")
		d = as_dict(payload)
		name = (d.get("case") or "").strip()
		if not frappe.db.exists("Livestock Disposal", name):
			frappe.throw(_("{0} is not a cull case.").format(name))

		doc = frappe.get_doc("Livestock Disposal", name)
		culling.assert_at(doc, {culling.APPROVED}, "posted")
		if doc.docstatus != 0:
			frappe.throw(_("{0} has already been posted.").format(name))

		flow = culling.assert_flow(doc.custom_cull_flow)
		culling.assert_may_post(flow)
		needs = culling.requires(flow)
		if needs["cause"] and not doc.custom_death_cause:
			frappe.throw(_("Say what she died of before posting it."))
		if needs["price"] and not (doc.sale_price and (doc.customer or doc.buyer_name)):
			frappe.throw(_("A sale needs a buyer and a price before it can be posted."))
		if flow == culling.GIFT and not doc.gifted_to:
			frappe.throw(_("Say who she was given to. A gift with no recipient is a loss."))

		herd_before = frappe.db.get_value("Animal", doc.animal, "current_herd")
		moved = _move_to_cull_herd(doc, herd_before, d.get("operator"))

		doc.submit()  # posts the asset and retires the animal
		doc.db_set("custom_review_status", culling.POSTED, update_modified=False)

		claim = _claim_for(doc) if flow == culling.MORTALITY else None

		return {
			"ok": True,
			"name": name,
			"status": culling.POSTED,
			"animal": doc.animal,
			"animal_status": frappe.db.get_value("Animal", doc.animal, "status"),
			"herd_before": herd_before,
			"herd_now": frappe.db.get_value("Animal", doc.animal, "current_herd"),
			"movement": moved,
			"sales_invoice": doc.get("sales_invoice"),
			"journal_entry": doc.get("writeoff_journal_entry"),
			"claim": claim,
		}

	return run(go, "livestock post_cull failed")


def _move_to_cull_herd(doc, herd_before, operator):
	"""Walk her into the holding herd, unless she is already standing in it."""
	herd = culling.ensure_cull_herd()
	if herd_before == herd:
		return None
	move = new_livestock_event(
		{"animal": doc.animal, "operator": operator,
		 "event_date": doc.disposal_date,
		 "remarks": _("{0} — {1}").format(doc.custom_cull_flow, doc.disposal_type)},
		"Movement",
	)
	move.new_herd = herd
	move.current_herd = herd_before or ""
	move.insert()
	move.submit()
	return move.name


def _claim_for(doc):
	"""Raise the insurance claim a covered death is owed.

	Raised automatically rather than left to somebody to remember: a claim
	window is measured in days, and the one moment the farm is certain to be in
	the system is the moment it records the death. It is a DRAFT — the claimed
	amount is the policy's arithmetic, not a demand anybody has made yet.
	"""
	from upande_livestock.serverscripts.culling.raise_insurance_claim import draft_claim

	try:
		return draft_claim(doc)
	except Exception:
		frappe.log_error(message=frappe.get_traceback(), title="Livestock insurance claim error")
		frappe.msgprint(
			_("The death was recorded but the insurance claim could not be drafted. "
			  "Raise it by hand."),
			alert=True, indicator="orange",
		)
		return None
