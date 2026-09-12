# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who may move a cull case to where, and what each flow demands on the way.

One module owns the chain so the six endpoints cannot each decide it
differently — which is the failure mode of approvals written per screen: the
gate holds on the page somebody tested and is missing on the one they did not.

FOUR FLOWS, NOT ONE FORM WITH A TYPE. An animal leaves for one of four reasons
and they differ in who decides, what evidence is required, and what posts:

    Sale       raised -> vet -> manager -> posted
    Disposal   raised -> vet -> posted          (the vet IS the decision)
    Gift       raised -> manager -> posted      (no health question)
    Mortality  recorded -> posted               (nobody decides a death)

Written as one form with a dropdown, the vet gate becomes optional on a sale
and the cause of death optional on a death. Each of those is the thing the flow
exists to enforce.
"""

import frappe
from frappe import _

SALE = "Sale"
DISPOSAL = "Disposal"
MORTALITY = "Mortality"
GIFT = "Gift"
FLOWS = (SALE, DISPOSAL, MORTALITY, GIFT)

DRAFT = "Draft"
AWAITING_VET = "Awaiting Vet"
AWAITING_APPROVAL = "Awaiting Approval"
APPROVED = "Approved"
REJECTED = "Rejected"
POSTED = "Posted"

#: Where a freshly raised case of each flow starts waiting.
FIRST_GATE = {
	SALE: AWAITING_VET,
	DISPOSAL: AWAITING_VET,
	GIFT: AWAITING_APPROVAL,
	MORTALITY: APPROVED,  # nobody approves a death; it is recorded, then posted
}

#: What each flow turns into on the Animal, and on the books.
TERMINAL_STATUS = {SALE: "Sold", DISPOSAL: "Culled", MORTALITY: "Dead", GIFT: "Transferred Out"}

#: The herd every departed animal ends up in. Her record stays readable; only
#: the head count and the feed run stop seeing her.
CULL_HERD = "Culled"

VET_ROLE = "Livestock Vet"
MANAGER_ROLE = "Livestock Manager"


def assert_flow(flow: str) -> str:
	if flow not in FLOWS:
		frappe.throw(_("{0} is not a cull flow. It is one of: {1}.").format(
			flow or "Nothing", ", ".join(FLOWS)))
	return flow


def _has(role: str) -> bool:
	roles = set(frappe.get_roles())
	return role in roles or "System Manager" in roles or "Administrator" in roles


def assert_vet() -> None:
	if not _has(VET_ROLE):
		frappe.throw(
			_("Only a {0} can record a veterinary verdict. Selling or disposing of an "
			  "animal on a health judgement nobody qualified made is the thing this "
			  "gate exists to stop.").format(VET_ROLE),
			frappe.PermissionError,
		)


def assert_manager() -> None:
	if not _has(MANAGER_ROLE):
		frappe.throw(
			_("Only a {0} can approve an animal leaving the farm.").format(MANAGER_ROLE),
			frappe.PermissionError,
		)


def assert_may_post(flow: str) -> None:
	"""Who is allowed to execute a departure.

	A DEATH IS NOT AN APPROVAL. Three of the flows are the farm choosing to lose
	an animal, and a manager signs for those. A death has already happened, and
	asking a manager to agree to it is asking him to approve the weather.

	On a site with the shipped permissions this changes nothing: raising a
	Livestock Disposal at all is management-only, so the only people who reach
	this are managers anyway. It is here because that is a permission decision,
	not a rule of the flow — a farm that lets its head herdsman record deaths
	gets the right behaviour by granting him the DocType, with no code change
	and no manager standing between a dead cow and her herd.
	"""
	if flow != MORTALITY:
		assert_manager()


def assert_at(doc, expected, what: str) -> None:
	"""Refuse to act on a case that is not waiting for this.

	Named in the message, because "invalid state" tells the operator nothing
	they can do. A case that has already been posted, or refused, or is still
	waiting on the vet, each needs a different next step.
	"""
	status = doc.get("custom_review_status") or DRAFT
	if status in expected:
		return
	if status == POSTED:
		frappe.throw(_("{0} has already left the farm — this case is closed.").format(doc.animal))
	if status == REJECTED:
		frappe.throw(_("This case was refused. Raise a new one rather than reviving it."))
	frappe.throw(
		_("This case is {0}, so it cannot be {1} yet.").format(status.lower(), what)
	)


def next_after_vet(flow: str, verdict: str) -> str:
	"""Where a case goes once the vet has seen her.

	A disposal IS the vet's call, so a recommendation to dispose needs nobody
	else; a sale still has to clear the manager. And a vet who says she is not
	fit to sell has ended that case — the farm does not get to overrule the
	health verdict by approving anyway.
	"""
	if verdict == "Not fit for sale" and flow == SALE:
		return REJECTED
	if flow == DISPOSAL:
		return APPROVED
	return AWAITING_APPROVAL


def requires(flow: str) -> dict:
	"""What a flow cannot be posted without."""
	return {
		SALE: {"buyer": True, "price": True, "cause": False},
		DISPOSAL: {"buyer": False, "price": False, "cause": False},
		GIFT: {"buyer": False, "price": False, "cause": False},
		MORTALITY: {"buyer": False, "price": False, "cause": True},
	}[flow]


def ensure_cull_herd() -> str:
	"""The holding herd, created on first use.

	Every departed animal is moved here rather than left in her milking group.
	`current_herd` is deliberately not cleared on a disposal — the record has to
	keep saying where she was — so without a move she stays listed under
	Lactating 1 forever, and every screen that reads a herd by its animals shows
	a cow that is not on the farm.

	Its head count settles at zero on its own: live_herd_count() counts only
	animals that are still active, and everything moved here is retired within
	the same posting.
	"""
	if not frappe.db.exists("Herds", CULL_HERD):
		herd = frappe.new_doc("Herds")
		herd.herd_name = CULL_HERD
		herd.description = _(
			"Animals that have left the farm — sold, died, disposed of or gifted. "
			"Kept so their records stay readable without counting against a "
			"working herd."
		)
		herd.insert(ignore_permissions=True)
		herd.submit()
	return CULL_HERD
