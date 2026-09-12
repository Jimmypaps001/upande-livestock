# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Everything leaving the farm, and who each case is waiting on."""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common import culling
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run

#: Who has to act next, said in the words the farm uses rather than a status
#: code. A queue that says "Awaiting Approval" to the vet and to the manager
#: alike is a queue neither of them checks.
WAITING_ON = {
	culling.AWAITING_VET: "the vet",
	culling.AWAITING_APPROVAL: "the manager",
	culling.APPROVED: "posting",
}

OPEN = (culling.AWAITING_VET, culling.AWAITING_APPROVAL, culling.APPROVED)


@frappe.whitelist()
def cull_board(payload=None):
	"""The open cases, the animals flagged for review, and what left recently.

	Three lists in one call because they are one screen and one decision: a
	marked cow with no case is work not yet started, an open case is work
	half-done, and the recent departures are what the farm has to show for it.
	Split across three endpoints they arrive at three different moments and the
	page flickers through states that never coexisted.
	"""

	def go():
		guard_read("Livestock Disposal")
		d = as_dict(payload)
		limit = min(int(d.get("limit") or 50), 200)

		cases = frappe.db.sql(
			"""SELECT d.name, d.animal, d.animal_name, d.disposal_date, d.disposal_type,
			          d.custom_cull_flow AS flow, d.custom_review_status AS status,
			          d.custom_evidence AS evidence, d.custom_was_productive AS was_productive,
			          d.custom_death_cause AS death_cause, d.custom_vet_verdict AS vet_verdict,
			          d.custom_vet_on AS vet_on, d.sale_price, d.buyer_name, d.gifted_to,
			          a.current_herd AS herd
			   FROM `tabLivestock Disposal` d
			   LEFT JOIN `tabAnimal` a ON a.name = d.animal
			   WHERE d.docstatus = 0 AND d.custom_review_status IN %(open)s
			   ORDER BY d.disposal_date DESC, d.creation DESC
			   LIMIT %(limit)s""",
			{"open": OPEN, "limit": limit}, as_dict=True,
		)
		for c in cases:
			c["waiting_on"] = WAITING_ON.get(c["status"], "nobody")
			c["was_productive"] = bool(c["was_productive"])
			c["sale_price"] = flt(c["sale_price"])

		flagged = frappe.db.sql(
			"""SELECT a.name, a.burn_name, a.current_herd AS herd,
			          a.custom_cull_reason AS reason, a.custom_cull_marked_on AS marked_on,
			          a.custom_cull_marked_by AS marked_by
			   FROM `tabAnimal` a
			   WHERE a.custom_cull_candidate = 1 AND a.disabled = 0
			     AND NOT EXISTS (
			         SELECT 1 FROM `tabLivestock Disposal` d
			         WHERE d.animal = a.name AND d.docstatus = 0
			           AND d.custom_review_status IN %(open)s)
			   ORDER BY a.custom_cull_marked_on DESC
			   LIMIT %(limit)s""",
			{"open": OPEN, "limit": limit}, as_dict=True,
		)

		recent = frappe.db.sql(
			"""SELECT d.name, d.animal, d.animal_name, d.disposal_date, d.disposal_type,
			          d.custom_cull_flow AS flow, d.custom_death_cause AS death_cause,
			          d.sale_price, d.sales_invoice, d.writeoff_journal_entry AS journal_entry,
			          c.name AS claim, c.status AS claim_status,
			          c.claimed_amount, c.payout_amount
			   FROM `tabLivestock Disposal` d
			   LEFT JOIN `tabLivestock Insurance Claim` c
			          ON c.disposal = d.name AND c.docstatus < 2
			   WHERE d.docstatus = 1
			   ORDER BY d.disposal_date DESC, d.creation DESC
			   LIMIT %(limit)s""",
			{"limit": limit}, as_dict=True,
		)
		for r in recent:
			r["sale_price"] = flt(r["sale_price"])

		return {
			"ok": True,
			"animals": _animals_on_the_farm(),
			"cases": cases,
			"flagged": flagged,
			"recent": recent,
			"counts": {
				"awaiting_vet": sum(1 for c in cases if c["status"] == culling.AWAITING_VET),
				"awaiting_approval": sum(
					1 for c in cases if c["status"] == culling.AWAITING_APPROVAL),
				"ready_to_post": sum(1 for c in cases if c["status"] == culling.APPROVED),
				"flagged": len(flagged),
			},
			"open_claims": _open_claims(),
		}

	return run(go, "livestock cull_board failed")


def _animals_on_the_farm():
	"""Who can still be culled: the animals that are still here.

	Served with the board rather than fetched separately so the search box is
	never a list of animals that have already left — which is what a page that
	loaded its own roster once and never again eventually becomes.
	"""
	return frappe.get_all(
		"Animal",
		filters={"disabled": 0, "status": "Active"},
		fields=["name", "burn_name", "sex", "current_herd", "breed", "date_of_birth", "image"],
		order_by="name",
		limit=2000,
	)


def _open_claims():
	"""Claims that have been raised and not yet settled.

	Surfaced on the culling screen rather than an accounting one because the
	person who recorded the death is the person who knows the insurer has gone
	quiet, and a drafted claim nobody sends is worth exactly nothing.
	"""
	return frappe.get_all(
		"Livestock Insurance Claim",
		filters={"status": ["in", ("Draft", "Submitted")], "docstatus": ["<", 2]},
		fields=["name", "animal", "policy", "claim_date", "cause", "claimed_amount", "status"],
		order_by="claim_date desc",
		limit=100,
	)
