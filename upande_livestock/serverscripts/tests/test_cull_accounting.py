# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What each cull flow does to the books.

A cow is a capitalised asset on this farm, so she cannot simply stop existing:
selling her raises revenue against the asset, and every other way of losing her
writes it off. The four flows differ in which of those two it is, and in one
case — a gift — the distinction is the entire accounting question, because a
gift looks like a sale to everyone except the ledger.

The postings themselves belong to api/assets.py and are tested there. What is
pinned here is WHICH posting each flow reaches, and with what terms, because
that is the part the cull chain decides.
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common import culling
from upande_livestock.serverscripts.culling.approve_cull import approve_cull
from upande_livestock.serverscripts.culling.post_cull import post_cull
from upande_livestock.serverscripts.culling.raise_cull import raise_cull
from upande_livestock.serverscripts.culling.vet_verdict import vet_verdict
from upande_livestock.serverscripts.tests.test_culling import _employee, _tidy
from upande_livestock.serverscripts.tests.test_operations import _make_cow

ANIMAL = "CULL-ACCT-1"
TARGET = "upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal"


def _a_customer():
	name = frappe.db.get_value("Customer", {}, "name")
	if name:
		return name
	return frappe.get_doc({
		"doctype": "Customer", "customer_name": "ZZ TEST " + frappe.generate_hash(length=8),
	}).insert(ignore_permissions=True).name


class TestWhichPostingEachFlowReaches(IntegrationTestCase):
	def setUp(self):
		_tidy(ANIMAL)
		_make_cow(ANIMAL, herd="Lactating group 1")
		self.addCleanup(_tidy, ANIMAL)
		self.sold = mock.MagicMock(return_value={})
		self.scrapped = mock.MagicMock(return_value={})

	def _post(self, case):
		with mock.patch(f"{TARGET}._sell_livestock_asset", self.sold), \
		     mock.patch(f"{TARGET}._scrap_livestock_asset", self.scrapped):
			got = post_cull({"case": case, "operator": _employee()})
		self.assertTrue(got.get("ok"), got.get("error"))
		return got

	def _sale(self, price=75000):
		case = raise_cull({"animal": ANIMAL, "flow": culling.SALE})["name"]
		vet_verdict({"case": case, "verdict": "Fit for sale"})
		approve_cull({"case": case, "sale_price": price, "customer": _a_customer(),
		              "buyer_name": "Juma"})
		return case

	def test_a_sale_raises_revenue_and_writes_nothing_off(self):
		self._post(self._sale())
		self.sold.assert_called_once()
		self.scrapped.assert_not_called()

	def test_the_sale_posts_the_price_that_was_approved(self):
		"""Not the price on the draft — the approval IS of the terms."""
		self._post(self._sale(price=91500))
		self.assertEqual(self.sold.call_args.kwargs["selling_amount"], 91500)

	def test_a_disposal_writes_the_asset_off(self):
		case = raise_cull({"animal": ANIMAL, "flow": culling.DISPOSAL})["name"]
		vet_verdict({"case": case, "verdict": "Recommends disposal"})
		self._post(case)
		self.scrapped.assert_called_once()
		self.sold.assert_not_called()

	def test_a_death_writes_the_asset_off(self):
		case = raise_cull({"animal": ANIMAL, "flow": culling.MORTALITY,
		                   "death_cause": "Poisoning"})["name"]
		self._post(case)
		self.scrapped.assert_called_once()
		self.sold.assert_not_called()

	def test_a_gift_writes_the_asset_off_rather_than_inventing_revenue(self):
		"""A gift looks like a sale to everyone except the ledger."""
		case = raise_cull({"animal": ANIMAL, "flow": culling.GIFT,
		                   "gifted_to": "Kaitet Primary School"})["name"]
		approve_cull({"case": case})
		self._post(case)
		self.scrapped.assert_called_once()
		self.sold.assert_not_called()
		self.assertEqual(frappe.db.get_value("Animal", ANIMAL, "status"), "Transferred Out")

	def test_the_write_off_carries_the_reason_she_left(self):
		"""An accountant reading the journal should not have to guess."""
		case = raise_cull({"animal": ANIMAL, "flow": culling.MORTALITY,
		                   "death_cause": "Disease — East Coast Fever"})["name"]
		self._post(case)
		self.assertEqual(self.scrapped.call_args.kwargs["reason"], "Died — Disease")

	def test_a_failed_posting_does_not_strand_the_animal(self):
		"""The books can be corrected later; a cow in limbo cannot.

		post_asset_disposal downgrades a posting failure to a warning on purpose
		— an uncapitalised animal, a missing account, a closed period. The
		departure still has to complete, or the farm is left with a dead animal
		that the system says is still milking.
		"""
		self.scrapped.side_effect = Exception("no asset account")
		case = raise_cull({"animal": ANIMAL, "flow": culling.MORTALITY,
		                   "death_cause": "Old age"})["name"]
		got = self._post(case)
		self.assertEqual(got["herd_now"], culling.CULL_HERD)
		self.assertEqual(frappe.db.get_value("Animal", ANIMAL, "status"), "Dead")
