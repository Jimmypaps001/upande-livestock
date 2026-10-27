# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A backdated record does not post money or stock.

The drug and semen paths learned this first (test_backdated_drugs.py). One
write never did, and it was reachable from the same amber Backdate toggle that
promises, in as many words, "You are not affecting stocks":

  Livestock Disposal  on_submit raises a Sales Invoice or an asset-scrap
                   Journal Entry.

It is pinned on what was posted, not on the absence of an exception: "nothing
threw" is what the old code did too.
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, today

from upande_livestock.serverscripts.disposal.record_disposal import record_disposal


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _an_animal():
	tag = frappe.generate_hash(length=10)
	return frappe.get_doc(
		{
			"doctype": "Animal",
			"tag_number": tag,
			"burn_name": tag,
			"sex": "Female",
			"status": "Active",
			"date_of_birth": add_months(today(), -30),
		}
	).insert(ignore_permissions=True)


class TestBackdatedDisposal(IntegrationTestCase):
	"""The asset postings are spied on rather than counted.

	No animal built by a test on this site is capitalised, so an unpatched run
	would post nothing either way and every assertion below would pass on the
	broken code too — the exact vacuous green this project has been bitten by.
	Patching the two posting functions makes the question answerable: were they
	REACHED? `post_asset_disposal` already downgrades their failures to a
	warning, so the call, not its outcome, is the behaviour under test.
	"""

	def setUp(self):
		self.addCleanup(_set_window, 0)
		_set_window(1)
		self.animal = _an_animal()
		self.addCleanup(frappe.db.rollback)

	def _a_customer(self):
		"""post_asset_disposal returns early on a Sold disposal with no customer
		or no price, so a sale test without both never reaches the posting at
		all and would pass on the unfixed code. Make one if the site has none —
		this site had no Customer records when the disposal flow was written."""
		name = frappe.db.get_value("Customer", {}, "name")
		if name:
			return name
		return frappe.get_doc(
			{"doctype": "Customer", "customer_name": "ZZ TEST " + frappe.generate_hash(length=8)}
		).insert(ignore_permissions=True).name

	def _dispose(self, disposal_date, disposal_type="Died — Natural Causes", **extra):
		self.sold = mock.MagicMock(return_value={})
		self.scrapped = mock.MagicMock(return_value={})
		target = "upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal"
		with mock.patch(f"{target}._sell_livestock_asset", self.sold), mock.patch(
			f"{target}._scrap_livestock_asset", self.scrapped
		):
			return record_disposal(
				{
					"animal": self.animal.name,
					"disposal_type": disposal_type,
					"disposal_date": disposal_date,
					"reason_details": "test",
					**extra,
				}
			)

	def test_a_backdated_death_posts_no_write_off(self):
		before = frappe.db.count("Journal Entry")
		res = self._dispose(add_days(today(), -60))
		self.assertNotIn("error", res, res.get("error"))
		self.scrapped.assert_not_called()
		self.assertEqual(frappe.db.count("Journal Entry"), before)

	def test_a_backdated_sale_posts_no_sales_invoice(self):
		before = frappe.db.count("Sales Invoice")
		res = self._dispose(
			add_days(today(), -60),
			disposal_type="Sold",
			customer=self._a_customer(),
			sale_price=45000,
		)
		self.assertNotIn("error", res, res.get("error"))
		self.sold.assert_not_called()
		self.assertEqual(frappe.db.count("Sales Invoice"), before)

	def test_a_live_sale_still_reaches_the_sales_invoice(self):
		"""The control that makes the assertion above mean something: with a
		customer and a price present, today's sale DOES reach the posting."""
		res = self._dispose(
			today(), disposal_type="Sold", customer=self._a_customer(), sale_price=45000
		)
		self.assertNotIn("error", res, res.get("error"))
		self.sold.assert_called_once()

	def test_a_backdated_disposal_still_retires_the_animal(self):
		"""The record and the retirement are the point; only the money waits."""
		res = self._dispose(add_days(today(), -60))
		doc = frappe.get_doc("Livestock Disposal", res["name"])
		self.assertEqual(doc.custom_is_backdated, 1)
		self.assertEqual(int(res["animal_disabled"]), 1)

	def test_a_live_death_still_reaches_the_write_off(self):
		"""The control: the suppression must not leak into today's work."""
		res = self._dispose(today())
		self.assertNotIn("error", res, res.get("error"))
		self.scrapped.assert_called_once()
