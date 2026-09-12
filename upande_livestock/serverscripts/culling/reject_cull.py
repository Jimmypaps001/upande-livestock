# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Refuse a cull case, with the reason on the record."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import culling
from upande_livestock.serverscripts.common.envelope import as_dict, guard_write, run


@frappe.whitelist()
def reject_cull(payload):
	"""Close a case without posting it.

	Either signatory may refuse, and the reason is required — a case that was
	turned down with no note is one the next person re-raises unchanged.
	"""

	def go():
		guard_write("Livestock Disposal")
		d = as_dict(payload)
		name = (d.get("case") or "").strip()
		reason = (d.get("reason") or "").strip()
		if not frappe.db.exists("Livestock Disposal", name):
			frappe.throw(_("{0} is not a cull case.").format(name))
		if not reason:
			frappe.throw(_("Say why. A case refused without a reason is one somebody "
			               "raises again unchanged."))

		doc = frappe.get_doc("Livestock Disposal", name)
		if not (culling._has(culling.VET_ROLE) or culling._has(culling.MANAGER_ROLE)):
			frappe.throw(_("Only a vet or a manager can refuse a cull case."),
			             frappe.PermissionError)
		culling.assert_at(
			doc, {culling.AWAITING_VET, culling.AWAITING_APPROVAL, culling.APPROVED}, "refused"
		)

		doc.db_set({
			"custom_review_status": culling.REJECTED,
			"custom_rejected_reason": reason,
		}, update_modified=False)
		return {"ok": True, "name": name, "status": culling.REJECTED}

	return run(go, "livestock reject_cull failed")
