# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The veterinary half of a cull decision."""

import frappe
from frappe import _
from frappe.utils import today

from upande_livestock.serverscripts.common import culling
from upande_livestock.serverscripts.common.envelope import as_dict, guard_write, run

VERDICTS = ("Fit for sale", "Not fit for sale", "Recommends disposal")


@frappe.whitelist()
def vet_verdict(payload):
	"""Record what the vet found, and move the case where that verdict sends it.

	A VERDICT OF "NOT FIT FOR SALE" ENDS THE CASE. The manager does not get to
	approve past it — that is the whole point of asking a vet before a buyer is
	involved, and an approval that could overrule the health finding would make
	the gate decorative.

	A disposal is the vet's own call, so a recommendation to dispose needs
	nobody else's signature; a sale still has to clear the manager afterwards.
	"""

	def go():
		guard_write("Livestock Disposal")
		culling.assert_vet()
		d = as_dict(payload)
		name = (d.get("case") or "").strip()
		verdict = (d.get("verdict") or "").strip()
		if verdict not in VERDICTS:
			frappe.throw(_("The verdict is one of: {0}.").format(", ".join(VERDICTS)))
		if not frappe.db.exists("Livestock Disposal", name):
			frappe.throw(_("{0} is not a cull case.").format(name))

		doc = frappe.get_doc("Livestock Disposal", name)
		culling.assert_at(doc, {culling.AWAITING_VET}, "seen by a vet")

		nxt = culling.next_after_vet(doc.custom_cull_flow, verdict)
		doc.db_set({
			"custom_vet_verdict": verdict,
			"custom_vet_notes": d.get("notes") or None,
			"custom_vet_by": frappe.session.user,
			"custom_vet_on": today(),
			"custom_review_status": nxt,
			"custom_rejected_reason": (
				_("The vet found her not fit for sale.") if nxt == culling.REJECTED else None
			),
		}, update_modified=False)

		return {"ok": True, "name": name, "verdict": verdict, "status": nxt}

	return run(go, "livestock vet_verdict failed")
