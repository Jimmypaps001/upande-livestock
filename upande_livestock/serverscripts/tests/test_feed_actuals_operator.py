# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who a day sheet's mix is recorded against.

A System Manager with no Employee (the desk's operator picker) names the
operator; anyone else is always recorded as their own linked Employee, whatever
they send; a linked user who sends nothing gets their own.

    bench --site mutara.local run-tests --app upande_livestock \
        --module upande_livestock.serverscripts.tests.test_feed_actuals_operator

The mix itself is stubbed: this is about which Employee is passed down, not about
moving stock.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common.employee import acting_employee
from upande_livestock.serverscripts.feeding import feed_actuals as FA

MANAGER = "feedop.manager@example.com"
STORES = "feedop.stores@example.com"
ORPHAN = "feedop.orphan@example.com"


def _user(email, roles):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	doc = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
	)
	for r in roles:
		doc.append("roles", {"role": r})
	doc.insert(ignore_permissions=True)


class TestFeedActualsOperator(IntegrationTestCase):
	def setUp(self):
		employees = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name", limit=2)
		if len(employees) < 2:
			raise unittest.SkipTest("needs two active Employees")
		self.mine, self.other = employees
		self._links = {e: frappe.db.get_value("Employee", e, "user_id") for e in employees}
		_user(MANAGER, ["System Manager"])
		_user(STORES, ["Livestock Stores"])
		_user(ORPHAN, ["Livestock Stores"])
		# Make sure nobody else claims these users, then link `mine` to STORES.
		frappe.db.set_value("Employee", self.mine, "user_id", STORES, update_modified=False)
		frappe.db.set_value("Employee", self.other, "user_id", None, update_modified=False)
		self.addCleanup(self._restore)
		self.seen = []

		def stub(herd, date=None, employee=None, allow_shortage=False):
			self.seen.append(employee)
			return {"status": "Manufactured"}

		patcher = patch.object(FA, "manufacture_day", side_effect=stub)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(frappe.set_user, "Administrator")

	def _restore(self):
		frappe.set_user("Administrator")
		for e, user in self._links.items():
			frappe.db.set_value("Employee", e, "user_id", user, update_modified=False)
		for u in (MANAGER, STORES, ORPHAN):
			frappe.delete_doc("User", u, force=True, ignore_permissions=True)

	def _mix(self, user, **kw):
		frappe.set_user(user)
		return FA.manufacture_feed_actuals("HERD", "2026-01-01", **kw)

	def test_a_system_manager_without_an_employee_mixes_for_the_chosen_operator(self):
		res = self._mix(MANAGER, employee=self.other)
		self.assertNotIn("error", res)
		self.assertEqual(self.seen, [self.other])

	def test_a_system_manager_without_an_employee_and_no_operator_is_told_to_choose(self):
		res = self._mix(MANAGER)
		self.assertIn("Choose who is feeding", res["error"])
		self.assertEqual(self.seen, [])

	def test_a_chosen_operator_must_exist_and_be_active(self):
		self.assertIn("There is no Employee", self._mix(MANAGER, employee="NO-SUCH-EMP")["error"])
		frappe.set_user("Administrator")
		frappe.db.set_value("Employee", self.other, "status", "Left", update_modified=False)
		self.addCleanup(frappe.db.set_value, "Employee", self.other, "status", "Active")
		self.assertIn("not an active Employee", self._mix(MANAGER, employee=self.other)["error"])
		self.assertEqual(self.seen, [])

	def test_a_normal_user_cannot_act_as_another_employee(self):
		res = self._mix(STORES, employee=self.other)
		self.assertNotIn("error", res)
		self.assertEqual(self.seen, [self.mine])

	def test_a_linked_user_works_with_no_employee_sent(self):
		for sent in (None, ""):
			self.seen.clear()
			res = self._mix(STORES, employee=sent)
			self.assertNotIn("error", res)
			self.assertEqual(self.seen, [self.mine])

	def test_a_user_with_no_employee_who_is_not_a_system_manager_is_refused(self):
		res = self._mix(ORPHAN, employee=self.other)
		self.assertIn("not registered as an employee", res["error"])
		self.assertEqual(self.seen, [])

	def test_acting_employee_for_the_administrator(self):
		frappe.set_user("Administrator")
		self.assertEqual(acting_employee(self.other), self.other)
