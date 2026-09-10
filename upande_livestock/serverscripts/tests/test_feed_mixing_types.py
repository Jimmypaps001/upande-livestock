# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The two feed mixes are named in the ledger, and named apart.

Concentrate mixing and ration mixing were both posting under the generic
"Manufacture" Stock Entry Type. The farm reads its stock movements by type, so
that made the mill and the mixer wagon one indistinguishable pile — and no
report could separate "what did we mill this week" from "what did we feed".

Two types now, both purpose "Manufacture", named alongside SCP's existing
"Chemical Mixing". What each test holds is that the entry carries the app's own
name for the kind of run it was, and specifically NOT the generic type: an
assertion that only checked the name would still pass if both mixes were given
the same one.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.patches.create_feed_mixing_stock_entry_types import TYPES
from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.feeding import _engine as feeding

GENERIC = "Manufacture"


def _a_manufacturable_concentrate():
	"""(item_code, bom_no, batch_qty) for a concentrate the stores can cover.

	A concentrate is a herd BOM line that has a recipe of its own — the same
	rule `concentrate_plan` uses to tell a concentrate from silage.
	"""
	seen = set()
	for herd_bom in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, pluck="bom"):
		for row in frappe.get_all(
			"BOM Item", filters={"parent": herd_bom, "parenttype": "BOM"}, fields=["item_code", "bom_no"]
		):
			bom_no = row.bom_no or frappe.db.get_value("Item", row.item_code, "default_bom")
			if not bom_no or bom_no in seen:
				continue
			seen.add(bom_no)
			qty = flt(frappe.db.get_value("BOM", bom_no, "quantity")) or 1.0
			try:
				feeding._assert_can_cover(row.item_code, bom_no, qty)
			except Exception:
				continue
			return row.item_code, bom_no, qty
	return None, None, None


def _a_feedable_herd():
	for herd in frappe.get_all(
		"Herds",
		filters=[["bom", "is", "set"], ["number_of_animals", ">", 0]],
		pluck="name",
		order_by="number_of_animals asc",
	):
		try:
			if feeding.get_herd_feeding_program(herd)["can_manufacture"]:
				return herd
		except frappe.ValidationError:
			continue
	return None


class TestFeedMixingStockEntryTypes(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_both_types_exist_with_the_manufacture_purpose(self):
		"""The patch's own contract. A type with the wrong purpose would not be
		labelled vaguely, it would be the wrong transaction — ERPNext reads
		purpose off the type."""
		for name, purpose in TYPES:
			self.assertTrue(frappe.db.exists("Stock Entry Type", name), f"{name} was never created")
			self.assertEqual(frappe.db.get_value("Stock Entry Type", name, "purpose"), purpose)

	def test_the_two_mixes_do_not_share_a_type(self):
		concentrate = livestock_stock.stock_entry_type_for(feeding.CONCENTRATE_MANUFACTURE)
		ration = livestock_stock.stock_entry_type_for(feeding.RATION_MANUFACTURE)
		self.assertNotEqual(concentrate, GENERIC)
		self.assertNotEqual(ration, GENERIC)
		self.assertNotEqual(concentrate, ration)

	def test_a_concentrate_run_posts_under_the_concentrate_type(self):
		item, bom_no, qty = _a_manufacturable_concentrate()
		if not item:
			raise unittest.SkipTest("no concentrate on this site can currently be mixed")
		# `manufacture_concentrate` commits, which would put this run beyond the
		# reach of the rollback. The commit is its own business — the caller's,
		# per common/stock's rule — so it is suppressed here rather than routed
		# around, and the endpoint is still exercised as the app calls it.
		with patch.object(frappe.db, "commit"):
			res = feeding.manufacture_concentrate(item, qty=qty, bom_no=bom_no)
		se = frappe.get_doc("Stock Entry", res["manufacture_stock_entry"])
		self.assertEqual(
			se.stock_entry_type,
			livestock_stock.stock_entry_type_for(feeding.CONCENTRATE_MANUFACTURE),
		)
		self.assertNotEqual(se.stock_entry_type, GENERIC)
		self.assertEqual(se.purpose, GENERIC)

	def test_a_ration_run_posts_under_the_ration_type(self):
		herd = _a_feedable_herd()
		if not herd:
			raise unittest.SkipTest("no herd on this site can currently be fed")
		employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not employee:
			raise unittest.SkipTest("no active Employee on this site")
		res = feeding.manufacture_herd_feed(herd, employee=employee)
		se = frappe.get_doc("Stock Entry", res["manufacture_stock_entry"])
		self.assertEqual(
			se.stock_entry_type, livestock_stock.stock_entry_type_for(feeding.RATION_MANUFACTURE)
		)
		self.assertNotEqual(se.stock_entry_type, GENERIC)
		self.assertEqual(se.purpose, GENERIC)
		# And the issue that follows it keeps its own name — the ration mix and
		# the feeding are two different movements and must stay two labels.
		issue = frappe.get_doc("Stock Entry", res["issue_stock_entry"])
		self.assertEqual(issue.stock_entry_type, livestock_stock.stock_entry_type_for("Feeding"))
