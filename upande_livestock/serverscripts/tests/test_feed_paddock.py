# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A herd with a paddock has its mix moved there after manufacture, and fed from there.

Manufacture lands in the mixing store; a Material Transfer takes it to the herd's paddock or
pen; the feeding issue reads from the paddock. A herd with no paddock is fed from the store as
before. Uses the Mutara seed (Starters stand in Feedlot Pen 1)."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.feeding import _engine
from upande_livestock.serverscripts.feeding.manufacture_feed import manufacture_feed
from upande_livestock.serverscripts.feeding.move_feed_to_paddock import move_feed_to_paddock

HERD = "Starters"


class TestFeedPaddock(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.get_value("Herds", HERD, "paddock"):
			self.skipTest("Starters has no paddock: run demo.seed_mutara_stores")
		self.paddock = frappe.db.get_value("Herds", HERD, "paddock")
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not self.employee:
			self.skipTest("no active Employee")
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()

	def test_the_mix_is_moved_to_the_paddock_and_issued_from_it(self):
		res = manufacture_feed(HERD, employee=self.employee)
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(res["paddock"], self.paddock)
		self.assertEqual(res["store"], frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse"))
		move = frappe.get_doc("Stock Entry", res["paddock_transfer_stock_entry"])
		self.assertEqual(move.purpose, "Material Transfer")
		self.assertEqual((move.items[0].s_warehouse, move.items[0].t_warehouse), (res["store"], self.paddock))
		issue = frappe.get_doc("Stock Entry", res["issue_stock_entry"])
		self.assertEqual(issue.items[0].s_warehouse, self.paddock)
		self.assertEqual(issue.items[0].qty, res["issued_qty"])

	def test_cancelling_the_feeding_takes_the_paddock_move_back_too(self):
		# BOMs made by another app can name a Work Order number a rolled-back run reuses; clear that
		# inside this (rolled back) transaction so the Work Order can be cancelled
		if frappe.db.has_column("BOM", "custom_work_order"):
			frappe.db.sql("update `tabBOM` set custom_work_order = null where custom_work_order is not null")
		res = manufacture_feed(HERD, employee=self.employee)
		self.assertNotIn("error", res, res.get("error"))
		frappe.get_doc("Livestock Event", res["livestock_event"]).cancel()
		for key in ("issue_stock_entry", "paddock_transfer_stock_entry", "manufacture_stock_entry"):
			self.assertEqual(frappe.db.get_value("Stock Entry", res[key], "docstatus"), 2, key)

	def test_a_herd_without_a_paddock_is_fed_from_the_store(self):
		frappe.db.set_value("Herds", HERD, "paddock", None)
		res = manufacture_feed(HERD, employee=self.employee)
		self.assertNotIn("error", res, res.get("error"))
		self.assertNotIn("paddock", res)
		issue = frappe.get_doc("Stock Entry", res["issue_stock_entry"])
		self.assertEqual(issue.items[0].s_warehouse, res["store"])

	def test_move_feed_to_paddock_needs_the_mix_in_the_store(self):
		res = move_feed_to_paddock(HERD, 5)
		self.assertIn("error", res)
		self.assertIn("holds", res["error"])

	def test_move_feed_to_paddock_without_a_paddock_is_refused(self):
		frappe.db.set_value("Herds", HERD, "paddock", None)
		res = move_feed_to_paddock(HERD, 5)
		self.assertIn("no paddock", res["error"])

	def test_herd_paddock_reads_the_link(self):
		self.assertEqual(_engine.herd_paddock(HERD), self.paddock)
		frappe.db.set_value("Herds", HERD, "paddock", None)
		self.assertIsNone(_engine.herd_paddock(HERD))
