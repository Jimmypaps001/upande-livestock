# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Create a Livestock Vet exactly as the ERP form would.

The record is made with `frappe.get_doc(...).insert()`, so everything the form
enforces is enforced here by the same controller: naming (VET-.####), mandatory
fields by type (an internal vet needs an Employee, an external one a name, a
phone and a Kenya Veterinary Board registration number), one vet per employee,
and the Employee/type being permanent. Nothing is re-implemented in this file
except the small conveniences the form gives (an internal vet's name, phone and
login are fetched from the Employee).

Payload (stable; the phone sends the same):
  vet_type            "Internal" | "External"   (required)
  employee            Employee id               (Internal: required)
  vet_name, phone     (External: required; Internal: taken from the Employee)
  email, qualification, licence_expiry (YYYY-MM-DD), practice_name, supplier
  registration_number (External: required)
  enabled             0|1, default 1
Answer: {"ok": true, "vet": {value, label, type, detail}} or {"error": "..."}.
"""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run

FIELDS = (
	"vet_type", "employee", "vet_name", "phone", "email", "registration_number",
	"qualification", "licence_expiry", "practice_name", "supplier",
)


def vet_doc_values(d):
	"""Clean payload -> Livestock Vet field values (strings trimmed, blanks dropped)."""
	vals = {}
	for f in FIELDS:
		v = d.get(f)
		if isinstance(v, str):
			v = v.strip()
		if v not in (None, ""):
			vals[f] = v
	vals["enabled"] = 0 if str(d.get("enabled", 1)) in ("0", "False", "false") else 1
	return vals


@frappe.whitelist()
def add_vet(payload=None):
	def go():
		# Creating a vet is configuration, not recording work: no Employee needed.
		guard("Livestock Vet", employee=False)
		d = as_dict(payload)
		vals = vet_doc_values(d)
		if vals.get("vet_type") not in ("Internal", "External"):
			frappe.throw(_("Choose the vet's type: Internal or External."))
		if vals["vet_type"] == "Internal" and vals.get("employee"):
			emp = frappe.db.get_value(
				"Employee", vals["employee"], ["employee_name", "cell_number", "user_id"], as_dict=True
			)
			if not emp:
				frappe.throw(_("Employee {0} does not exist.").format(vals["employee"]))
			vals.setdefault("vet_name", emp.employee_name)
			if emp.cell_number:
				vals.setdefault("phone", emp.cell_number)
			if emp.user_id:
				vals.setdefault("user", emp.user_id)
		doc = frappe.get_doc({"doctype": "Livestock Vet", **vals}).insert()
		return {
			"ok": True,
			"vet": {
				"value": doc.name,
				"label": doc.vet_name or doc.name,
				"type": doc.vet_type,
				"detail": " · ".join(
					x for x in (doc.vet_type, doc.practice_name if doc.vet_type == "External" else None) if x
				),
			},
		}

	return run(go, "livestock add_vet failed")
