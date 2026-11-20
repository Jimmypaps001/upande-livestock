"""Add or change a Livestock Sire. The manager's job: the can map's `manage_sires`."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, run

EDITABLE = ("sire_name", "sire_code", "sire_type", "semen_item", "animal", "sexed", "active", "breed")
MANAGERS = ("Livestock Manager", "System Manager")


def _assert_manager():
	roles = set(frappe.get_roles())
	if frappe.session.user != "Administrator" and not roles & set(MANAGERS):
		frappe.throw(_("Only a Livestock Manager may change the sires."), frappe.PermissionError)


@frappe.whitelist()
def save_sire(payload=None):
	def go():
		_assert_manager()
		d = as_dict(payload)
		fields = {k: d.get(k) for k in EDITABLE if k in d}
		for k in ("semen_item", "animal", "sire_code", "breed"):
			if k in fields and not (fields[k] or "").strip():
				fields[k] = None
		if d.get("name"):
			doc = frappe.get_doc("Livestock Sire", d["name"])
			doc.update(fields)
			doc.save()
		else:
			if not (fields.get("sire_name") or "").strip():
				frappe.throw(_("A sire needs a name."))
			doc = frappe.get_doc({"doctype": "Livestock Sire", "active": 1, **fields}).insert()
		return {"ok": True, "name": doc.name}

	return run(go, "livestock save_sire failed")
