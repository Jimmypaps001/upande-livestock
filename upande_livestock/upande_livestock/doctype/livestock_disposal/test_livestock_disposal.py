# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.desk.search import search_link
from frappe.tests import IntegrationTestCase

from upande_livestock.api.animal import STATUS_BY_DISPOSAL_TYPE

# This site has no standard ERPNext test fixtures (e.g. "All Departments"), so
# following the dependency graph into Herds -> BOM -> Item -> Department blows up.
# test_livestock_event.py / test_livestock_diagnosis.py hit the same wall; mirror
# their fix and build the fixtures we need by hand instead.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Animal",
	"Herds",
	"Customer",
	"Company",
	"Employee",
	"Account",
	"Cost Center",
	"Journal Entry",
]


def make_animal(tag):
	if frappe.db.exists("Animal", tag):
		doc = frappe.get_doc("Animal", tag)
		doc.db_set("disabled", 0)
		doc.db_set("status", "Active")
		return doc
	return frappe.get_doc(
		{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
	).insert()


def _purge_animal(tag):
	if frappe.db.exists("Animal", tag):
		frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
	frappe.db.commit()


def _purge_disposal(name):
	if frappe.db.exists("Livestock Disposal", name):
		# Livestock Disposal is submittable: delete_doc(force=True) bypasses link
		# checks, not the submitted-record guard, so a submitted test doc must be
		# cancelled first or every cleanup here throws "Submitted Record cannot be
		# deleted".
		doc = frappe.get_doc("Livestock Disposal", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Livestock Disposal", name, force=True, ignore_permissions=True)
	frappe.db.commit()


def _purge_customer(name):
	if frappe.db.exists("Customer", name):
		frappe.delete_doc("Customer", name, force=True, ignore_permissions=True)
	frappe.db.commit()


class TestLivestockDisposal(IntegrationTestCase):
	def setUp(self):
		self.animal = make_animal("TEST-DISPOSE-1")
		# Registered first so it runs LAST (addCleanup is LIFO): any disposal
		# created against this animal in a test method is a child that must be
		# deleted before the parent Animal, since delete_doc(force=True) does
		# not cascade.
		self.addCleanup(_purge_animal, self.animal.name)

	def _disposal(self, disposal_type, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Disposal",
				"animal": self.animal.name,
				"disposal_date": "2026-09-01",
				"disposal_type": disposal_type,
				**kwargs,
			}
		)
		doc.insert()
		self.addCleanup(_purge_disposal, doc.name)
		doc.submit()
		return doc

	def test_status_map_covers_every_disposal_type(self):
		options = frappe.get_meta("Livestock Disposal").get_field("disposal_type").options
		for option in [o for o in options.split("\n") if o.strip()]:
			self.assertIn(option, STATUS_BY_DISPOSAL_TYPE, f"{option} has no status mapping")

	def test_animal_gains_a_disabled_field_that_is_read_only(self):
		field = frappe.get_meta("Animal").get_field("disabled")
		self.assertIsNotNone(field)
		self.assertTrue(field.read_only)

	def test_customer_and_sale_price_are_optional_on_the_doctype(self):
		"""customer/sale_price are deliberately unenforced server-side: this site
		has zero Customer records and all 10 existing Sold disposals carry only a
		free-text buyer_name. A mandatory_depends_on wouldn't even help — Frappe
		16 only enforces it in the browser — and a validate() check would break
		those 10 rows on amend.
		"""
		meta = frappe.get_meta("Livestock Disposal")
		customer_field = meta.get_field("customer")
		sale_price_field = meta.get_field("sale_price")
		self.assertFalse(customer_field.reqd)
		self.assertFalse(customer_field.mandatory_depends_on)
		self.assertFalse(sale_price_field.reqd)
		self.assertFalse(sale_price_field.mandatory_depends_on)

	@patch(
		"upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.sell_livestock_asset"
	)
	@patch("frappe.msgprint")
	def test_sold_without_customer_or_price_warns_and_still_retires(self, mock_msgprint, mock_sell):
		doc = self._disposal("Sold")

		mock_sell.assert_not_called()
		self.assertEqual(mock_msgprint.call_count, 1)
		self.assertEqual(doc.docstatus, 1)
		self.animal.reload()
		self.assertEqual(self.animal.status, "Sold")
		self.assertTrue(self.animal.disabled)

	@patch(
		"upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.scrap_livestock_asset"
	)
	def test_died_routes_to_scrap(self, mock_scrap):
		self._disposal("Died — Disease")
		mock_scrap.assert_called_once()

	@patch(
		"upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.sell_livestock_asset"
	)
	def test_sold_routes_to_sell(self, mock_sell):
		customer = frappe.db.get_value("Customer", {}, "name")
		if not customer:
			customer = frappe.get_doc({"doctype": "Customer", "customer_name": "TEST-BUYER"}).insert().name
			self.addCleanup(_purge_customer, customer)
		self._disposal("Sold", customer=customer, sale_price=50000)
		mock_sell.assert_called_once()

	@patch(
		"upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.scrap_livestock_asset"
	)
	def test_status_and_disabled_are_set(self, _mock_scrap):
		self._disposal("Died — Accident")
		self.animal.reload()
		self.assertEqual(self.animal.status, "Dead")
		self.assertTrue(self.animal.disabled)

	@patch(
		"upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.scrap_livestock_asset"
	)
	def test_uncapitalised_animal_disposes_with_a_warning_not_a_throw(self, mock_scrap):
		mock_scrap.side_effect = frappe.ValidationError("not capitalised")
		doc = self._disposal("Culled (Farm Use)")
		self.assertEqual(doc.docstatus, 1)
		self.animal.reload()
		self.assertTrue(self.animal.disabled)

	@patch(
		"upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.scrap_livestock_asset"
	)
	def test_disabled_animal_is_hidden_from_link_search(self, _mock_scrap):
		self._disposal("Died — Natural Causes")
		found = [r["value"] for r in search_link("Animal", "TEST-DISPOSE-1")]
		self.assertNotIn("TEST-DISPOSE-1", found)

	def test_active_animal_is_visible_in_link_search(self):
		animal = make_animal("TEST-VISIBLE-1")
		self.addCleanup(_purge_animal, animal.name)
		found = [r["value"] for r in search_link("Animal", "TEST-VISIBLE-1")]
		self.assertIn("TEST-VISIBLE-1", found)
