# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the insurer actually did with a claim."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard_write, run


@frappe.whitelist()
def settle_insurance_claim(payload):
	"""Record what the insurer actually did with the claim.

	A payout that differs from the amount claimed is the normal case, so the
	settled figure is recorded beside the claimed one rather than overwriting
	it: the gap between the two is the only evidence the farm has when
	negotiating the next policy.
	"""

	def go():
		guard_write("Livestock Insurance Claim")
		d = as_dict(payload)
		name = (d.get("claim") or "").strip()
		status = (d.get("status") or "").strip()
		if status not in ("Submitted", "Paid", "Rejected"):
			frappe.throw(_("A claim is Submitted, Paid or Rejected."))
		if not frappe.db.exists("Livestock Insurance Claim", name):
			frappe.throw(_("{0} is not a claim.").format(name))

		claim = frappe.get_doc("Livestock Insurance Claim", name)
		if claim.status == "Paid" and status != "Paid":
			frappe.throw(_("{0} has already been paid.").format(name))

		claim.status = status
		if status == "Paid":
			amount = flt(d.get("payout_amount"))
			if amount <= 0:
				frappe.throw(_("Say how much was paid."))
			claim.payout_amount = amount
			claim.payout_date = d.get("payout_date") or today()
			claim.journal_entry = d.get("journal_entry") or None
		if d.get("remarks"):
			claim.remarks = d["remarks"]
		claim.save(ignore_permissions=True)

		return {"ok": True, "name": name, "status": status,
		        "payout_amount": flt(claim.payout_amount),
		        "shortfall": flt(claim.claimed_amount) - flt(claim.payout_amount)}

	return run(go, "livestock settle_insurance_claim failed")
