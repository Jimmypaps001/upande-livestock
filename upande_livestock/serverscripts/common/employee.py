"""Who is doing the work, for the endpoints that must stamp an Employee.

A desk user is a User; a data-entry form needs the Employee that user is
linked to, because that is what Livestock Event / Livestock Health Treatment /
etc. record as the operator. `employee_or_throw` exists because several
endpoints must refuse to save rather than silently record a blank operator
when a user has no linked Employee.
"""

import frappe
from frappe import _


def current_employee():
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def employee_or_throw(employee=None):
	employee = employee or current_employee()
	if not employee:
		frappe.throw(
			_("No Employee is linked to your user ({0}). Select an operator or link an Employee.").format(
				frappe.session.user
			)
		)
	return employee


def acting_employee(employee=None):
	"""The Employee an action is recorded against.

	Only a System Manager or Administrator may name someone other than their
	own linked Employee (the desk's operator picker). Everyone else always
	gets their own, whatever they send. A named Employee must exist and not
	have left. With nobody named, it is the session user's linked Employee,
	or None when there is none (the caller decides how to refuse).
	"""
	mine = current_employee()
	named = (employee or "").strip() if isinstance(employee, str) else employee
	if not named:
		return mine
	user = frappe.session.user
	if user != "Administrator" and "System Manager" not in frappe.get_roles(user):
		return mine or None
	status = frappe.db.get_value("Employee", named, "status")
	if status is None:
		frappe.throw(_("There is no Employee {0}. Pick the operator from the list.").format(named))
	if status != "Active":
		frappe.throw(_("{0} is not an active Employee, so cannot be named as the operator.").format(named))
	return named
