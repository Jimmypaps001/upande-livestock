# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Take back a shoat record: a count event (its pair too), a treatment (its stock issue too) or a weight sample."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import shoats
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run

KINDS = {"count_event": "Herd Count Event", "treatment": "Herd Treatment", "weight_sample": "Herd Weight Sample"}


@frappe.whitelist()
def cancel_shoat_record(payload=None):
	def go():
		d = as_dict(payload)
		doctype = KINDS.get(d.get("kind"))
		if not doctype:
			frappe.throw(_("Kind must be one of: {0}.").format(", ".join(KINDS)))
		guard(doctype)
		name = d.get("name")
		if not name or not frappe.db.exists(doctype, name):
			frappe.throw(_("{0} {1} does not exist.").format(doctype, name or ""))
		doc = frappe.get_doc(doctype, name)
		doc.flags.ignore_permissions = True
		herd = doc.herd
		if doc.docstatus == 1:
			doc.cancel()
		elif doctype == "Herd Weight Sample":
			frappe.delete_doc(doctype, name, ignore_permissions=True)
		else:
			frappe.throw(_("{0} is already cancelled.").format(name))
		return {"ok": True, "cancelled": {"kind": d.get("kind"), "name": name}, "herd": herd,
		        "head": shoats.head(herd), **shoats.live_weight(herd), "warnings": []}

	return run(go, "livestock cancel_shoat_record failed")
