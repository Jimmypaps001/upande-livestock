# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The nutritionist: keeps the feed library and balances rations, moves no stock.

Asked as a real user holding only Livestock Nutritionist, with an Employee
behind them so the employee gate is not what stops the refusals.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from upande_livestock.serverscripts.common.envelope import NUTRITIONIST_ROLE
from upande_livestock.serverscripts.feeding.feed_nutrition import feed_nutrition, livestock_feeds
from upande_livestock.serverscripts.feeding.manufacture_all_feeds import manufacture_all_feeds
from upande_livestock.serverscripts.feeding.manufacture_feed import manufacture_feed
from upande_livestock.serverscripts.feeding.set_herd_ration import set_herd_ration
from upande_livestock.serverscripts.settings.posting_day import posting_day
from upande_livestock.serverscripts.tests.test_employee_gate import _drop_all, _user


class TestLivestockNutritionistRole(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.herd, self.bom = frappe.db.get_value(
			"Herds", {"bom": ["is", "set"]}, ["name", "bom"]
		) or (None, None)
		if not self.herd:
			raise unittest.SkipTest("no herd with a standing ration on this site")
		self.lines = [
			{"item_code": r.item_code, "qty": flt(r.qty)}
			for r in frappe.get_all(
				"BOM Item", filters={"parent": self.bom}, fields=["item_code", "qty"], order_by="idx"
			)
		]
		self.email = _user(NUTRITIONIST_ROLE)
		frappe.db.commit()
		self.addCleanup(_drop_all)

	def test_the_role_ships_with_the_app(self):
		self.assertTrue(frappe.db.exists("Role", NUTRITIONIST_ROLE))

	def test_it_reads_the_day_and_the_feed_library(self):
		frappe.set_user(self.email)
		day = posting_day()
		self.assertTrue(day.get("ok"), day)
		self.assertEqual(day["today"], today())
		self.assertIn(NUTRITIONIST_ROLE, day["roles"])
		self.assertTrue(livestock_feeds().get("ok"))
		self.assertTrue(feed_nutrition(lines=frappe.as_json(self.lines)).get("ok"))

	def test_it_keeps_the_feed_library(self):
		frappe.set_user(self.email)
		for right in ("read", "write", "create"):
			self.assertTrue(frappe.has_permission("Livestock Feed", right), right)
		self.assertTrue(frappe.has_permission("Herds", "read"))
		self.assertFalse(frappe.has_permission("Herds", "write"))

	def test_it_saves_a_herds_ration(self):
		# The herd's own ration sent back: passes the BOM guard, changes nothing.
		frappe.set_user(self.email)
		out = set_herd_ration({"herd": self.herd, "lines": self.lines})
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(frappe.db.get_value("Herds", self.herd, "bom"), out["bom"])

	def test_it_moves_no_stock(self):
		frappe.set_user(self.email)
		for out in (
			manufacture_all_feeds(date=today(), preview=1),
			manufacture_feed(self.herd),
		):
			self.assertTrue(out.get("error"), out)
			self.assertNotEqual(out.get("code"), "not_employee", out)
		for doctype in ("Stock Entry", "Work Order"):
			self.assertFalse(frappe.has_permission(doctype, "create"), doctype)
		for doctype in ("Animal", "Livestock Event"):
			self.assertFalse(frappe.has_permission(doctype, "read"), doctype)
		self.assertFalse(frappe.has_permission("BOM", "submit"))
