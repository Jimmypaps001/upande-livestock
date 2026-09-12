# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Claim on a policy when an insured animal dies."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


def covering_policy(animal, on_date):
	"""The policy that covered her ON THE DAY SHE DIED, not the one live today.

	A claim is settled against the cover that was in force at the loss. Reading
	only `status = Active` would refuse a claim on a death two days before the
	policy lapsed — which is precisely the claim a farm most needs to make, and
	the one it is most likely to be recording late.
	"""
	on_date = getdate(on_date or today())
	rows = frappe.db.sql(
		"""SELECT p.name, p.insurer, p.policy_number, p.payout_percent,
		          p.start_date, p.end_date, a.insured_value
		   FROM `tabLivestock Insurance Policy` p
		   JOIN `tabLivestock Insurance Policy Animal` a ON a.parent = p.name
		   WHERE a.animal = %s
		     AND p.status != 'Cancelled'
		     AND (p.start_date IS NULL OR p.start_date <= %s)
		     AND (p.end_date IS NULL OR p.end_date >= %s)
		   ORDER BY p.end_date DESC LIMIT 1""",
		(animal, on_date, on_date), as_dict=True,
	)
	return rows[0] if rows else None


def claim_amount(policy, book_value=0.0):
	"""What the policy owes on this animal.

	The insured value is what the farm agreed with the insurer she was worth,
	so it leads. Book value is the fallback for a policy written at farm level
	with no per-animal figure — better an amount the accountant can argue down
	than a claim of zero that nobody chases.
	"""
	base = flt(policy.get("insured_value")) or flt(book_value)
	percent = flt(policy.get("payout_percent"))
	return flt(base * percent / 100.0) if percent else flt(base)


def draft_claim(disposal):
	"""Draft the claim a covered death is owed, or return None if uninsured.

	Idempotent: posting the same disposal twice cannot raise two claims against
	one carcass.
	"""
	existing = frappe.db.exists("Livestock Insurance Claim",
	                            {"disposal": disposal.name, "docstatus": ["<", 2]})
	if existing:
		return {"name": existing, "existing": True}

	policy = covering_policy(disposal.animal, disposal.disposal_date)
	if not policy:
		return None

	claim = frappe.new_doc("Livestock Insurance Claim")
	claim.animal = disposal.animal
	claim.policy = policy["name"]
	claim.disposal = disposal.name
	claim.claim_date = today()
	claim.cause = disposal.get("custom_death_cause") or disposal.disposal_type
	claim.claimed_amount = claim_amount(policy, disposal.get("book_value"))
	claim.status = "Draft"
	claim.remarks = _("Raised automatically when {0} was recorded dead.").format(disposal.animal)
	claim.insert(ignore_permissions=True)

	return {
		"name": claim.name,
		"insurer": policy.get("insurer"),
		"policy": policy["name"],
		"claimed_amount": claim.claimed_amount,
		"existing": False,
	}


@frappe.whitelist()
def raise_insurance_claim(payload):
	"""Raise a claim by hand, for a death recorded before the policy was loaded."""

	def go():
		guard("Livestock Insurance Claim")
		d = as_dict(payload)
		name = (d.get("disposal") or "").strip()
		if not frappe.db.exists("Livestock Disposal", name):
			frappe.throw(_("{0} is not a disposal.").format(name))
		doc = frappe.get_doc("Livestock Disposal", name)
		claim = draft_claim(doc)
		if not claim:
			frappe.throw(
				_("No policy covered {0} on {1}, so there is nothing to claim.")
				.format(doc.animal, doc.disposal_date)
			)
		return {"ok": True, **claim}

	return run(go, "livestock raise_insurance_claim failed")
