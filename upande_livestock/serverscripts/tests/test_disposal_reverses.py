# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A disposal writes the asset off correctly, and cancelling one undoes it.

The write-off Journal Entry was built by hand and credited the depreciation
expense account instead of the fixed-asset account, so the cow stayed on the
balance sheet. And there was no on_cancel: a cancelled disposal left her
retired, disabled and written off.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.disposal.record_disposal import record_disposal
from upande_livestock.serverscripts.herds.buy_in_animal import buy_in_animal
from upande_livestock.serverscripts.tests.test_buy_in import HERD, _forget
from upande_livestock.serverscripts.tests.test_culling import _employee


def _forget_disposals(animal):
	for name in frappe.get_all("Livestock Disposal", filters={"animal": animal}, pluck="name"):
		doc = frappe.get_doc("Livestock Disposal", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Livestock Disposal", name, force=True, ignore_permissions=True)
	frappe.db.commit()


class TestADisposalIsUndoneByCancelling(IntegrationTestCase):
	def setUp(self):
		got = buy_in_animal({"sex": "Female", "herd": HERD, "name_given": "ZZ DISPOSED",
		                     "purchase_value": 90000, "operator": _employee()})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.animal, self.asset = got["animal"], got["asset"]
		self.assertTrue(self.asset, "the bought animal was not capitalised")
		self.addCleanup(_forget, self.animal)
		self.addCleanup(_forget_disposals, self.animal)

	def _died(self):
		got = record_disposal({"animal": self.animal, "disposal_type": "Died — Disease",
		                       "operator": _employee()})
		self.assertTrue(got.get("ok"), got.get("error"))
		return frappe.get_doc("Livestock Disposal", got["name"])

	def test_the_write_off_takes_the_cow_off_the_fixed_asset_account(self):
		disposal = self._died()
		self.assertEqual(frappe.db.get_value("Asset", self.asset, "status"), "Scrapped")
		je = frappe.get_doc("Journal Entry", disposal.writeoff_journal_entry)
		fixed_asset_account = frappe.db.get_value(
			"Asset Category Account",
			{"parent": frappe.db.get_value("Asset", self.asset, "asset_category"),
			 "company_name": je.company},
			"fixed_asset_account",
		)
		credited = {row.account for row in je.accounts if row.credit_in_account_currency}
		self.assertIn(fixed_asset_account, credited)

	def test_cancelling_brings_her_back(self):
		disposal = self._died()
		herd = frappe.db.get_value("Animal", self.animal, "current_herd")
		heads = frappe.db.get_value("Herds", herd, "number_of_animals")
		je = disposal.writeoff_journal_entry
		disposal.cancel()
		animal = frappe.db.get_value("Animal", self.animal, ["status", "disabled"], as_dict=True)
		self.assertEqual((animal.status, animal.disabled), ("Active", 0))
		self.assertEqual(frappe.db.get_value("Herds", herd, "number_of_animals"), heads + 1)
		self.assertNotEqual(frappe.db.get_value("Asset", self.asset, "status"), "Scrapped")
		self.assertEqual(frappe.db.get_value("Journal Entry", je, "docstatus"), 2)

	def test_a_cull_case_waiting_on_review_cannot_be_submitted_from_the_form(self):
		doc = frappe.get_doc({
			"doctype": "Livestock Disposal", "animal": self.animal,
			"disposal_type": "Culled (Farm Use)", "custom_review_status": "Awaiting Vet",
			"disposal_date": frappe.utils.today(),
		}).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "disabled"), 0)
