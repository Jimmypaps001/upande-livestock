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
