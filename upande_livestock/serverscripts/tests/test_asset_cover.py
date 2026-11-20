# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Insurance cover through Upande Asset, and the ERPNext way of selling a cow.

Upande Asset's insurance module may be missing from a site (it is a separate app
on its own branch), so the cover wrappers are pinned against stand-ins for its
functions, and everything that touches the real module skips when it is absent.
"""

import sys
import types
import unittest
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import asset_cover
from upande_livestock.serverscripts.disposal.sell_livestock_asset import _sell_livestock_asset
from upande_livestock.serverscripts.tests.test_cull_accounting import _a_customer
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge

MODS = "upande_asset.upande_asset.insurance"


def _row(end, status="Active", row_status="Active"):
	return frappe._dict(policy="INS-POL-1", policy_type="Theft", policy_number="N-9", insurer="SUP",
	                    insurer_name="Jubilee", start_date=add_days(today(), -100), end_date=end,
	                    status=status, row_status=row_status, sum_insured=90000)


def _fake_insurance(rows):
	utils = types.ModuleType(f"{MODS}.utils")
	utils.get_covering_rows = lambda asset, on_date=None, **kw: rows
	utils.get_expiring_threshold = lambda: 30
	pkg = types.ModuleType(MODS)
	pkg.utils = utils
	return {MODS: pkg, f"{MODS}.utils": utils}


class TestCoverRead(IntegrationTestCase):
	def test_no_asset_is_its_own_state(self):
		self.assertEqual(asset_cover.cover_for_asset(None)["state"], "no_asset")

	def test_no_insurance_module_answers_unavailable_not_an_error(self):
		with mock.patch.object(asset_cover, "available", return_value=False):
			self.assertEqual(asset_cover.cover_for_asset("A-1")["state"], "unavailable")

	def _read(self, rows):
		fake = _fake_insurance(rows)
		saved = {k: sys.modules.get(k) for k in fake}
		sys.modules.update(fake)
		try:
			with mock.patch.object(asset_cover, "available", return_value=True):
				return asset_cover.cover_for_asset("A-1")
		finally:
			for k, v in saved.items():
				if v is None:
					sys.modules.pop(k, None)
				else:
					sys.modules[k] = v

	def test_a_running_policy_is_insured_with_its_details(self):
		got = self._read([_row(add_days(today(), 200))])
		self.assertEqual(got["state"], "insured")
		self.assertEqual(got["policyNumber"], "N-9")
		self.assertEqual(got["insurer"], "Jubilee")
		self.assertEqual(got["sumInsured"], 90000)
		self.assertEqual(got["daysLeft"], 200)

	def test_a_policy_ending_soon_is_expiring(self):
		self.assertEqual(self._read([_row(add_days(today(), 10))])["state"], "expiring")

	def test_a_cancelled_or_removed_row_is_no_cover(self):
		with mock.patch.object(asset_cover, "_from_native", return_value=asset_cover._empty("none")):
			self.assertEqual(self._read([_row(add_days(today(), 50), status="Cancelled")])["state"], "none")
			self.assertEqual(self._read([_row(add_days(today(), 50), row_status="Removed")])["state"], "none")

	def test_cover_that_ended_reads_expired_from_the_asset_fields(self):
		native = {"insurance_end_date": add_days(today(), -5), "policy_number": "N-1",
		          "insurance_policy": "P", "insurer": "J", "insured_value": "100"}
		got = asset_cover._from_native(native)
		self.assertEqual(got["state"], "expired")
		self.assertEqual(got["policyNumber"], "N-1")
		self.assertEqual(asset_cover._from_native({})["state"], "none")

	def test_states_by_date(self):
		self.assertEqual(asset_cover._state_for(add_days(today(), 90)), "insured")
		self.assertEqual(asset_cover._state_for(add_days(today(), 3)), "expiring")
		self.assertEqual(asset_cover._state_for(add_days(today(), -1)), "expired")
		self.assertEqual(asset_cover._state_for(None), "none")

	def test_an_animal_with_no_asset_is_no_asset_in_the_list(self):
		tag = "ZZ COVER NOASSET"
		_make_cow(tag)
		self.addCleanup(_purge, "Animal", tag)
		with mock.patch.object(asset_cover, "available", return_value=True):
			self.assertEqual(asset_cover.covers_for_animals([tag])[tag], "no_asset")
		with mock.patch.object(asset_cover, "available", return_value=False):
			self.assertEqual(asset_cover.covers_for_animals([tag])[tag], "unavailable")


class TestPutUnderCover(IntegrationTestCase):
	def setUp(self):
		self.tag = "ZZ COVER COW"
		_make_cow(self.tag)
		self.addCleanup(_purge, "Animal", self.tag)

	def _get_value(self, doctype, name, fields=None, *a, **kw):
		if doctype == "Insurance Policy":
			return (add_days(today(), -30), add_days(today(), 300))
		if doctype == "Animal":
			return "ACC-ASS-X"
		if doctype == "Asset":
			return 120000
		return real_get_value(doctype, name, fields, *a, **kw)

	def test_it_calls_upande_assets_own_endorse_with_add_assets(self):
		frappe.db.set_value("Animal", self.tag, "asset_link", None)
		with mock.patch.object(asset_cover, "available", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				asset_cover.put_under_cover(self.tag, "INS-POL-1")  # no asset

	def test_payload_and_answer(self):
		with mock.patch.object(asset_cover, "available", return_value=True), \
		     mock.patch.object(asset_cover, "cover_for_asset", return_value=asset_cover._empty("none")), \
		     mock.patch("frappe.db.get_value", side_effect=self._get_value), \
		     mock.patch("frappe.call", return_value={"status": "Requested", "endorsement_group": "g1"}) as call:
			got = asset_cover.put_under_cover(self.tag, "INS-POL-1", endorsement_no="E1")
		args, kw = call.call_args
		self.assertEqual(args[0], asset_cover.ENDORSE)
		self.assertEqual(kw["policy"], "INS-POL-1")
		self.assertEqual(kw["action"], "Add Assets")
		self.assertEqual(kw["payload"]["endorsement_no"], "E1")
		self.assertEqual(kw["payload"]["assets"], [{"asset": "ACC-ASS-X", "sum_insured": 120000}])
		self.assertEqual(got["status"], "Requested")

	def test_already_covered_is_refused_and_missing_module_says_so(self):
		with mock.patch.object(asset_cover, "available", return_value=False):
			with self.assertRaises(frappe.ValidationError):
				asset_cover.put_under_cover(self.tag, "P")
		with mock.patch.object(asset_cover, "available", return_value=True), \
		     mock.patch("frappe.db.get_value", return_value="ACC-ASS-X"), \
		     mock.patch.object(asset_cover, "cover_for_asset", return_value={"state": "insured"}):
			with self.assertRaises(frappe.ValidationError):
				asset_cover.put_under_cover(self.tag, "P")


real_get_value = frappe.db.get_value


class TestSellThroughErpnext(IntegrationTestCase):
	"""The sale invoice is ERPNext's make_sales_invoice, with the cow's asset row."""

	def setUp(self):
		for doctype, name in (("Item", "herd"), ("Asset Category", "Herd")):
			if not frappe.db.exists(doctype, name):
				raise unittest.SkipTest(f"{doctype} {name} not on this site")
		self.tag = "ZZ SELL COW"
		self.asset = frappe.db.get_value("Asset", {"asset_category": "Herd", "docstatus": 1,
		                                           "status": "Submitted"}, "name")
		if not self.asset:
			raise unittest.SkipTest("no submitted Herd asset on this site")
		_make_cow(self.tag)
		frappe.db.set_value("Animal", self.tag, {"asset_link": self.asset, "is_capitalised": 1})
		self.addCleanup(_purge, "Animal", self.tag)
		frappe.db.savepoint("sell_test")
		self.addCleanup(frappe.db.rollback, save_point="sell_test")
		# This bench's Sales Invoice has a mandatory custom Farm and no selling price
		# list; give the test what a configured farm has, inside the savepoint.
		company = frappe.db.get_value("Asset", self.asset, "company")
		cur = frappe.get_cached_value("Company", company, "default_currency")
		if not frappe.db.get_single_value("Selling Settings", "selling_price_list"):
			pl = frappe.get_doc({"doctype": "Price List", "price_list_name": "ZZ SELL PL " + frappe.generate_hash(length=5),
			                     "selling": 1, "currency": cur}).insert(ignore_permissions=True)
			frappe.db.set_single_value("Selling Settings", "selling_price_list", pl.name)
		self.farm = frappe.db.get_value("Farm", {}, "name") if frappe.db.exists("DocType", "Farm") else None
		if frappe.get_meta("Sales Invoice").has_field("custom_farm") and not self.farm:
			raise unittest.SkipTest("Sales Invoice needs a Farm and none exists")

	def test_draft_invoice_carries_the_asset_row_and_disposal_account(self):
		got = _sell_livestock_asset(animal=self.tag, customer=_a_customer(), selling_amount=90000,
		                            posting_date=today(), farm=self.farm)
		si = frappe.get_doc("Sales Invoice", got["sales_invoice"])
		self.assertEqual(si.docstatus, 0)
		row = si.items[0]
		self.assertEqual(row.is_fixed_asset, 1)
		self.assertEqual(row.asset, self.asset)
		self.assertEqual(row.rate, 90000)
		self.assertEqual(row.qty, 1)
		company = frappe.db.get_value("Asset", self.asset, "company")
		disposal = frappe.get_cached_value("Company", company, "disposal_account")
		if disposal:
			self.assertEqual(row.income_account, disposal)
