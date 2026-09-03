# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Every livestock flow that consumes something must post a Stock Entry.

That is the property these tests defend, one flow at a time: vaccination and
deworming issue their drug rows, a health case issues its treatments, a service
issues a semen straw. Milking and feeding already posted theirs and are covered by
their own modules.

These tests need stock to draw down. They skip rather than fail when the drug store
has not been seeded (demo/seed_test_stock.py), because an unseeded site is a missing
fixture, not a broken feature — and a red suite on a fresh clone teaches people to
ignore red suites. Seed with:

    bench --site <site> execute upande_livestock.demo.seed_test_stock.run
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.api.operations import (
	create_health_case,
	create_husbandry_event,
	create_service_event,
)
from upande_livestock.api.test_operations import _assert_ok, _employee, _make_cow, _purge, _purge_events_for


def _stocked_drug():
	"""A drug item with a positive balance in the configured drug store, or None."""
	warehouse = livestock_stock.drug_warehouse()
	if not warehouse:
		return None, None
	row = frappe.db.sql(
		"""SELECT item_code, actual_qty FROM `tabBin`
		   WHERE warehouse = %s AND actual_qty > 0
		   ORDER BY actual_qty DESC LIMIT 1""",
		(warehouse,),
		as_dict=True,
	)
	return (row[0].item_code, warehouse) if row else (None, warehouse)


class StockSeededTestCase(IntegrationTestCase):
	"""Base class that skips the whole case when there is nothing to issue."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.drug_item, cls.warehouse = _stocked_drug()
		if not cls.drug_item:
			raise unittest.SkipTest(
				"No drug stock on hand — run upande_livestock.demo.seed_test_stock.run first."
			)


class TestHusbandryStockIssue(StockSeededTestCase):
	def setUp(self):
		self.cow = _make_cow("ZZ STK HUSB COW")
		self.addCleanup(_purge, "Animal", self.cow.name)
		self.addCleanup(_purge_events_for, self.cow.name)

	def _record(self, event_type):
		return _assert_ok(
			self,
			create_husbandry_event(
				{
					"event_type": event_type,
					"animal": self.cow.name,
					"event_date": today(),
					"operator": _employee(),
					"drugs": [
						{
							"item_code": self.drug_item,
							"qty": 1,
							"source_warehouse": self.warehouse,
							"dosage": "20 ml",
						}
					],
				}
			),
			f"create_husbandry_event({event_type})",
		)

	def test_vaccination_posts_a_material_issue(self):
		res = self._record("Vaccination")
		self.assertTrue(res["stock_entry"], "Vaccination must post a Stock Entry")
		se = frappe.get_doc("Stock Entry", res["stock_entry"])
		self.addCleanup(_purge, "Stock Entry", se.name)
		# The ledger has to say what the drugs were for. The type is the named
		# one; the purpose stays Material Issue so stock behaves identically.
		self.assertEqual(se.stock_entry_type, "Vaccination")
		self.assertEqual(se.purpose, "Material Issue")
		self.assertEqual(se.docstatus, 1)
		self.assertEqual(se.items[0].item_code, self.drug_item)
		self.assertEqual(se.items[0].s_warehouse, self.warehouse)

	def test_deworming_posts_a_material_issue(self):
		res = self._record("Deworming")
		self.assertTrue(res["stock_entry"], "Deworming must post a Stock Entry")
		self.addCleanup(_purge, "Stock Entry", res["stock_entry"])
		se = frappe.get_doc("Stock Entry", res["stock_entry"])
		self.assertEqual(se.stock_entry_type, "Deworming")
		self.assertEqual(se.purpose, "Material Issue")

	def test_the_drug_row_records_the_issue(self):
		res = self._record("Vaccination")
		self.addCleanup(_purge, "Stock Entry", res["stock_entry"])
		refs = frappe.get_all(
			"Livestock Drug Issue",
			filters={"parent": res["name"]},
			fields=["item_code", "stock_entry_ref"],
		)
		self.assertEqual(len(refs), 1)
		self.assertEqual(refs[0].stock_entry_ref, res["stock_entry"])

	def test_a_procedure_type_issues_nothing(self):
		"""Hoof Trimming consumes no stock, so it must not post an issue."""
		res = _assert_ok(
			self,
			create_husbandry_event(
				{
					"event_type": "Hoof Trimming",
					"animal": self.cow.name,
					"event_date": today(),
					"operator": _employee(),
				}
			),
			"create_husbandry_event(Hoof Trimming)",
		)
		self.assertFalse(res["stock_entry"])

	def test_an_unknown_type_is_rejected(self):
		res = create_husbandry_event(
			{"event_type": "Milking", "animal": self.cow.name, "operator": _employee()}
		)
		self.assertFalse(res.get("ok"))

	def test_a_blank_drug_row_does_not_fail_the_event(self):
		"""A half-filled drug line is dropped, not treated as an error."""
		res = _assert_ok(
			self,
			create_husbandry_event(
				{
					"event_type": "Vaccination",
					"animal": self.cow.name,
					"event_date": today(),
					"operator": _employee(),
					"drugs": [{"item_code": "", "qty": 0}],
				}
			),
			"create_husbandry_event with a blank drug row",
		)
		self.assertFalse(res["stock_entry"])
		self.assertEqual(res["drugs_issued"], 0)


class TestTreatmentStockIssue(StockSeededTestCase):
	def test_health_case_treatments_post_an_issue(self):
		cow = _make_cow("ZZ STK TREAT COW")
		self.addCleanup(_purge, "Animal", cow.name)
		self.addCleanup(_purge_events_for, cow.name)
		res = _assert_ok(
			self,
			create_health_case(
				{
					"animal": cow.name,
					"opened_date": today(),
					"opened_by": _employee(),
					"case_status": "Open",
					"presenting_symptoms": "Off feed, warm to touch",
					"treatments": [
						{"drug_item": self.drug_item, "dosage": "20 ml", "route": "IM (Intramuscular)"}
					],
				}
			),
			"create_health_case with a treatment",
		)
		self.addCleanup(_purge, "Livestock Health Case", res["name"])
		self.assertEqual(res["treatments"], 1)
		self.assertTrue(res["drug_stock_entry"], "A treated case must post a drug issue")
		self.addCleanup(_purge, "Stock Entry", res["drug_stock_entry"])
		se = frappe.get_doc("Stock Entry", res["drug_stock_entry"])
		self.assertEqual(se.stock_entry_type, "Animal Treatment")
		self.assertEqual(se.purpose, "Material Issue")
		self.assertEqual(se.items[0].item_code, self.drug_item)

	def test_a_case_with_no_drug_posts_nothing(self):
		cow = _make_cow("ZZ STK NODRUG COW")
		self.addCleanup(_purge, "Animal", cow.name)
		self.addCleanup(_purge_events_for, cow.name)
		res = _assert_ok(
			self,
			create_health_case(
				{
					"animal": cow.name,
					"opened_date": today(),
					"opened_by": _employee(),
					"presenting_symptoms": "Mild lameness, monitoring only",
				}
			),
			"create_health_case with no treatment",
		)
		self.addCleanup(_purge, "Livestock Health Case", res["name"])
		self.assertFalse(res["drug_stock_entry"])


class TestServiceStockIssue(IntegrationTestCase):
	"""A Service issues a semen straw.

	This reverses a rule that operations.py used to state as an invariant and enforce
	with an assert. It is a deliberate reversal — an A.I. does consume a straw.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.semen_item = livestock_stock.default_semen_item()
		warehouse = livestock_stock.semen_warehouse()
		on_hand = (
			flt(
				frappe.db.get_value(
					"Bin", {"item_code": cls.semen_item, "warehouse": warehouse}, "actual_qty"
				)
			)
			if (cls.semen_item and warehouse)
			else 0
		)
		if on_hand <= 0:
			raise unittest.SkipTest(
				"No semen stock on hand — run upande_livestock.demo.seed_test_stock.run first."
			)

	def test_service_posts_a_semen_issue(self):
		cow = _make_cow("ZZ STK SERVICE COW")
		self.addCleanup(_purge, "Animal", cow.name)
		self.addCleanup(_purge_events_for, cow.name)
		res = _assert_ok(
			self,
			create_service_event(
				{
					"animal": cow.name,
					"service_type": "A.I.",
					"service_date": today(),
					"operator": _employee(),
				}
			),
			"create_service_event",
		)
		self.assertTrue(res["stock_entry"], "A Service must issue a semen straw")
		self.addCleanup(_purge, "Stock Entry", res["stock_entry"])
		se = frappe.get_doc("Stock Entry", res["stock_entry"])
		self.assertEqual(se.stock_entry_type, "Semen Issue")
		self.assertEqual(se.purpose, "Material Issue")
		self.assertEqual(se.items[0].item_code, self.semen_item)
		self.assertEqual(flt(se.items[0].qty), 1.0)
