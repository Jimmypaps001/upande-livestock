# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""For Accounts: every loss that raised a claim, and where the claim stands."""

import frappe

from upande_livestock.serverscripts.common import loss
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def loss_claims(payload=None, status=None):
	"""For Accounts: every loss that raised a claim, with where the claim stands."""

	def go():
		guard_read("Livestock Loss")
		d = loss.merge(payload, status=status)
		rows = frappe.get_all(
			"Livestock Loss", filters={"claim": ["is", "set"]},
			fields=["name", "animal", "animal_name", "scenario", "incident_date", "claim", "claim_status",
			        "status", "disposal", "sales_invoice", "missing_documents"],
			order_by="incident_date desc, creation desc", limit=500)
		live = {c.name: c for c in frappe.get_all(
			"Insurance Claim", filters={"name": ["in", [r.claim for r in rows]]} if rows else {"name": ""},
			fields=["name", "status", "amount_claimed", "amount_approved", "amount_received",
			        "outstanding_amount"])}
		out = []
		for r in rows:
			c = live.get(r.claim)
			item = dict(r, incident_date=str(r.incident_date))
			if c:
				item.update({"claim_status": c.status, "amount_claimed": c.amount_claimed,
				             "amount_approved": c.amount_approved, "amount_received": c.amount_received,
				             "outstanding_amount": c.outstanding_amount})
			if d.get("status") and item.get("claim_status") != d["status"]:
				continue
			out.append(item)
		return {"ok": True, "claims": out, "requirement": loss.required_status()}

	return run(go, "livestock loss_claims failed")
