# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who may record, tested as real users rather than as Administrator.

Two rules, both enforced on the server because the phone only records facts:

* A user with no Employee linked to them is view-only. Every recording endpoint
  refuses them with the same words (guards.require_employee, reached through
  envelope.guard).
* Each farm role can use the screens it is given: it reads what the app reads
  for it, and records what it is meant to record, with no ERPNext role beyond
  its own.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common import guards
from upande_livestock.serverscripts.common.envelope import LIVESTOCK_ROLES, guard, guard_stock
from upande_livestock.serverscripts.mobile.record_animal_event import record_animal_event
from upande_livestock.serverscripts.mobile.record_feeding import record_feeding
from upande_livestock.serverscripts.settings.posting_day import posting_day

PREFIX = "zz-gate-"


def _email(role):
	return f"{PREFIX}{role.split()[-1].lower()}@example.com"


def link_employee(email):
	"""Give `email` an Employee (user_id = email), so the recording gate lets them in.

	Written with db_insert: a site Server Script rejects a new Employee unless
	the saver holds Security Head, which has nothing to do with these tests.
	Tests that sign in as a farm role to prove a different gate need this, since
	a user with no Employee is refused before that gate is reached.
	"""
	if frappe.db.exists("Employee", {"user_id": email}):
		return
	emp = frappe.get_doc({
		"doctype": "Employee", "first_name": "zzgate", "last_name": email.split("@")[0][-8:],
		"employee_name": "zzgate " + email.split("@")[0][-8:], "gender": "Male",
		"date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
		"company": frappe.db.get_value("Company", {}, "name"), "user_id": email,
		"status": "Active", "national_id": "ZZ" + email.split("@")[0], "tax_id": "ZZ" + email.split("@")[0],
	})
	emp.set_new_name()
	emp.set_user_and_timestamp()
	emp.db_insert()


def _user(role, with_employee=True):
	"""A user with exactly one farm role, and (optionally) an Employee behind it.

	The Employee is written with db_insert: a site Server Script rejects a new
	Employee unless the saver holds Security Head, which says nothing about this.
	"""
	email = _email(role) if with_employee else _email(role).replace("@", "-none@")
	if not frappe.db.exists("User", email):
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": "zzgate", "send_welcome_email": 0,
			"user_type": "System User", "roles": [{"role": role}],
		}).insert(ignore_permissions=True)
	if with_employee:
		link_employee(email)
	return email


def _drop_all():
	frappe.set_user("Administrator")
	for email in frappe.get_all("User", filters={"name": ["like", f"{PREFIX}%"]}, pluck="name"):
		frappe.db.delete("Employee", {"user_id": email})
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.db.commit()


class _AsUser(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		_drop_all()


class TestNonEmployeeIsViewOnly(_AsUser):
	def setUp(self):
		self.hand = _user("Livestock Manager", with_employee=False)
		frappe.db.commit()
		frappe.set_user(self.hand)

	def test_posting_day_says_who_you_are(self):
		out = posting_day()
		self.assertFalse(out["is_employee"])
		self.assertIsNone(out["employee"])
		self.assertIn("today", out)

	def test_every_recording_endpoint_refuses_with_a_code(self):
		for call in (
			lambda: record_animal_event({"type": "Heat Detection", "animal": "x", "event_date": "2026-01-01"}),
			lambda: record_feeding({"action": "manufacture", "herd": "x"}),
		):
			out = call()
			self.assertEqual(out.get("code"), "not_employee", out)
			self.assertEqual(out["error"], guards.NOT_EMPLOYEE)

	def test_the_shared_guard_is_where_it_lives(self):
		with self.assertRaises(guards.NotEmployee):
			guard("Livestock Event")

	def test_config_endpoints_opt_out(self):
		guard("Livestock Settings", employee=False)  # a manager's settings save is not a recording

	def test_a_system_manager_keeps_the_desk_bypass(self):
		frappe.set_user("Administrator")
		guards.require_employee()  # must not raise


class TestAnEmployeePassesTheGate(_AsUser):
	def test_attendant_with_employee_is_not_stopped_by_the_gate(self):
		email = _user("Livestock Attendant")
		frappe.db.commit()
		frappe.set_user(email)
		out = posting_day()
		self.assertTrue(out["is_employee"])
		self.assertTrue(out["employee"])
		self.assertTrue(out["employee_name"])
		res = record_animal_event({"type": "Heat Detection", "animal": "x", "event_date": "2026-01-01"})
		self.assertNotEqual(res.get("code"), "not_employee")

	def test_a_left_employee_does_not_count(self):
		email = _user("Livestock Attendant")
		frappe.db.set_value("Employee", {"user_id": email}, "status", "Left")
		frappe.set_user(email)
		self.assertFalse(guards.employee_status()["is_employee"])


class TestEachRoleHasWhatItsScreensRead(_AsUser):
	"""The reads every farm role needs just to sign in and look at an animal."""

	def test_every_farm_role_reads_what_the_app_reads(self):
		for role in LIVESTOCK_ROLES:
			email = _user(role)
			frappe.db.commit()
			for doctype in ("Animal", "Livestock Event", "Livestock Health Case", "Livestock Settings"):
				self.assertTrue(
					frappe.has_permission(doctype, "read", user=email),
					f"{role} cannot read {doctype}",
				)

	def test_employee_lookup_goes_through_the_server(self):
		from upande_livestock.serverscripts.people.employee_options import employee_options

		email = _user("Livestock Attendant")
		frappe.db.commit()
		frappe.set_user(email)
		out = employee_options({})
		self.assertTrue(out.get("ok"), out)
		self.assertTrue(out["mine"])
		self.assertFalse(frappe.has_permission("Employee", "read"))  # and no broader role was handed out

	def test_stock_is_booked_by_stores_and_managers_only(self):
		for role, allowed in (
			("Livestock Stores", True), ("Livestock Manager", True),
			("Livestock Attendant", False),
			("Livestock Breeder", False), ("Livestock Vet", False),
		):
			frappe.set_user("Administrator")
			frappe.set_user(_user(role))
			if allowed:
				guard_stock("Work Order", "Stock Entry")
			else:
				with self.assertRaises(frappe.PermissionError):
					guard_stock("Work Order", "Stock Entry")

	def test_each_role_may_create_what_it_records(self):
		for role, doctype in (
			("Livestock Attendant", "Livestock Event"),
			("Livestock Breeder", "Livestock Event"),
			("Livestock Vet", "Livestock Diagnosis"),
			("Livestock Vet", "Livestock Health Case"),
			("Livestock Manager", "Livestock Event"),
		):
			frappe.set_user("Administrator")
			email = _user(role)
			frappe.db.commit()
			frappe.set_user(email)
			guard(doctype)  # raises if refused

	def test_a_role_cannot_record_another_roles_thing(self):
		frappe.set_user(_user("Livestock Attendant"))
		with self.assertRaises(frappe.PermissionError):
			guard("Livestock Diagnosis")
