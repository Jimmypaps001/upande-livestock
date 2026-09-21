"""Charging livestock stock movements to a cost centre that exists.

ERPNext refuses a Stock Entry outright — "Cost Center is mandatory for Item
{0}" — when the item's expense account is a profit-and-loss one and no cost
centre can be found. It looks in exactly two places: the Item Default for that
company, then the Company's own default.

On live, neither is set for dairy. Karen Roses, which the feed engine posts
under, has a blank default cost centre; 134 Dairy Feed items, 219 Dairy Drugs
and 429 Dairy Others carry no buying cost centre; and the Item Default rows
that exist for the feed meals are against other companies with the cost centre
empty. Six of the eight feed runs that failed in the week to 2026-09-21 died
there, naming `Dry Cows  Meal`.

These tests pin the fallback order and, more importantly, the two refusals: a
row that already has a cost centre is never rewritten, and nothing is invented
when there is no answer — a wrong cost centre is a real accounting error,
quieter and worse than the refusal it replaces.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import test_cost_center as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import cost_center as CC


class Row(dict):
	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError as e:
			raise AttributeError(k) from e

	def __setattr__(self, k, v):
		self[k] = v


class Doc:
	def __init__(self, rows, company=None):
		self._rows = rows
		self.company = company

	def get(self, key):
		return self._rows if key == "items" else None


class TestWhereTheCostCentreComesFrom(unittest.TestCase):
	def test_the_setting_wins(self):
		with patch.object(frappe.db, "get_single_value", return_value="Dairy - KR"):
			self.assertEqual(CC.resolve("Karen Roses"), "Dairy - KR")

	def test_the_company_default_is_the_fallback(self):
		"""A site that has configured its company properly needs no setting."""
		with patch.object(frappe.db, "get_single_value", return_value=None), patch.object(
			frappe.db, "get_value", return_value="Main - KR"
		):
			self.assertEqual(CC.resolve("Karen Roses"), "Main - KR")

	def test_nothing_anywhere_means_nothing(self):
		"""Not a guess. ERPNext's own refusal names the item; a wrong cost
		centre is a silent accounting error."""
		with patch.object(frappe.db, "get_single_value", return_value=None), patch.object(
			frappe.db, "get_value", return_value=None
		):
			self.assertIsNone(CC.resolve("Karen Roses"))

	def test_a_site_that_has_not_migrated_falls_through_rather_than_raising(self):
		"""`get_single_value` raises ValidationError for a field that does not
		exist yet, so a deploy landing before its migrate would take feeding
		down instead of behaving as it did the day before."""
		meta = frappe.get_meta(CC.SETTINGS)
		with patch.object(meta, "has_field", return_value=False), patch.object(
			frappe, "get_meta", return_value=meta
		), patch.object(frappe.db, "get_value", return_value="Main - KR"), patch.object(
			frappe.db, "get_single_value", side_effect=AssertionError("must not be asked")
		):
			self.assertEqual(CC.resolve("Karen Roses"), "Main - KR")


class TestStampingTheRows(unittest.TestCase):
	def test_blank_rows_are_filled(self):
		rows = [Row(cost_center=""), Row(cost_center=None)]
		with patch.object(CC, "resolve", return_value="Dairy - KR"):
			self.assertEqual(CC.stamp(Doc(rows, "Karen Roses")), 2)
		self.assertEqual([r["cost_center"] for r in rows], ["Dairy - KR"] * 2)

	def test_a_row_that_already_has_one_is_never_rewritten(self):
		"""Whether it came from an Item Default or a person, it was deliberate.
		This is a fallback, not a policy."""
		rows = [Row(cost_center="Chosen - KR")]
		with patch.object(CC, "resolve", return_value="Dairy - KR"):
			self.assertEqual(CC.stamp(Doc(rows, "Karen Roses")), 0)
		self.assertEqual(rows[0]["cost_center"], "Chosen - KR")

	def test_no_cost_centre_available_changes_nothing(self):
		rows = [Row(cost_center="")]
		with patch.object(CC, "resolve", return_value=None):
			self.assertEqual(CC.stamp(Doc(rows, "Karen Roses")), 0)
		self.assertEqual(rows[0]["cost_center"], "")

	def test_a_document_with_no_rows_is_fine(self):
		with patch.object(CC, "resolve", return_value="Dairy - KR"):
			self.assertEqual(CC.stamp(Doc([], "Karen Roses")), 0)

	def test_it_never_takes_the_run_down(self):
		"""A feed run must not be lost because this helper had a bad day."""
		rows = [Row(cost_center="")]
		with patch.object(CC, "resolve", side_effect=RuntimeError("boom")):
			self.assertEqual(CC.stamp(Doc(rows, "Karen Roses")), 0)
		self.assertEqual(rows[0]["cost_center"], "")

	def test_the_company_comes_off_the_document_when_not_given(self):
		rows = [Row(cost_center="")]
		seen = {}

		def spy(company=None):
			seen["company"] = company
			return "Dairy - KR"

		with patch.object(CC, "resolve", side_effect=spy):
			CC.stamp(Doc(rows, "Westwood Dairies"))
		self.assertEqual(seen["company"], "Westwood Dairies")


class TestTheSettingIsReallyThere(unittest.TestCase):
	def test_the_field_exists_on_livestock_settings(self):
		"""A typo in the JSON would leave resolve() silently on the company
		default forever, which is the behaviour this was written to replace."""
		self.assertTrue(
			frappe.get_meta(CC.SETTINGS).has_field("custom_default_cost_center")
		)

	def test_it_points_at_Cost_Center(self):
		f = frappe.get_meta(CC.SETTINGS).get_field("custom_default_cost_center")
		self.assertEqual(f.fieldtype, "Link")
		self.assertEqual(f.options, "Cost Center")
