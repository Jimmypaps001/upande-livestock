# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The people who treat the herd, as records the system can measure.

A vet used to be a name typed into a note, which cannot be counted, listed or
paid. An INTERNAL vet is a farm employee and is paid through payroll; an
EXTERNAL vet is a registered practitioner the farm calls in and pays a fee
(through their Supplier, when they have one).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class LivestockVet(Document):
	def validate(self):
		self.validate_link_is_permanent()
		if self.vet_type == "Internal":
			self.validate_internal()
		else:
			self.validate_external()
		self.warn_if_licence_expired()

	def validate_link_is_permanent(self):
		"""The Vet-Employee link is fixed once the vet exists.

		The JSON flag (set_only_once) only guards the form; an API update must not
		turn an internal vet external, or point them at another employee, either.
		Past work and fees are recorded against this vet on the strength of what
		they are.
		"""
		if self.is_new():
			return
		before = self.get_doc_before_save() or frappe.get_doc("Livestock Vet", self.name)
		for field, label in (("vet_type", _("Type")), ("employee", _("Employee"))):
			if (before.get(field) or None) != (self.get(field) or None):
				frappe.throw(
					_("{0} cannot be changed once the vet is created. Disable this vet and "
					  "create another.").format(label),
					title=_("Vet link is permanent"),
				)

	def validate_internal(self):
		if not self.employee:
			frappe.throw(_("An internal vet is an employee. Choose the Employee."))
		other = frappe.db.get_value(
			"Livestock Vet", {"employee": self.employee, "name": ("!=", self.name)}, "name"
		)
		if other:
			frappe.throw(
				_("{0} is already the vet record for {1}.").format(other, self.employee),
				title=_("Duplicate vet"),
			)
		# An employee is not a supplier: an internal vet's time is paid by payroll.
		self.supplier = None
		self.registration_number = self.registration_number or None

	def validate_external(self):
		# Not an employee, so nothing to fetch from and nothing to keep.
		self.employee = None
		for field, label in (
			("vet_name", _("Vet Name")),
			("registration_number", _("Kenya Veterinary Board Registration No.")),
			("phone", _("Phone")),
		):
			if not (self.get(field) or "").strip():
				frappe.throw(_("{0} is required for an external vet.").format(label))

	def warn_if_licence_expired(self):
		if self.licence_expiry and getdate(self.licence_expiry) < getdate(today()):
			frappe.msgprint(
				_("{0}'s licence expired on {1}.").format(self.vet_name or self.name, self.licence_expiry),
				indicator="orange",
				alert=True,
			)


def vet_for_user(user=None):
	"""The enabled Livestock Vet whose login is `user` (default: the session user).

	Matched on the vet's own `user`, then on the Employee linked to that user, so
	an internal vet whose record was saved before the employee had a login still
	resolves. None when the user is not a vet.
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	name = frappe.db.get_value("Livestock Vet", {"user": user, "enabled": 1}, "name")
	if name:
		return name
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if employee:
		return frappe.db.get_value("Livestock Vet", {"employee": employee, "enabled": 1}, "name")
	return None


@frappe.whitelist()
def get_current_vet():
	"""The signed-in user's vet record, for forms to default to."""
	frappe.has_permission("Livestock Vet", "read", throw=True)
	name = vet_for_user()
	if not name:
		return None
	return frappe.db.get_value("Livestock Vet", name, ["name", "vet_name", "vet_type"], as_dict=True)
