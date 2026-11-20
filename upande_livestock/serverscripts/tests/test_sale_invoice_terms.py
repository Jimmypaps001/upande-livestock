# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Selling a culled animal to a chosen buyer gives Accounts a complete draft.

The buyer is a real Customer, the terms are worked out from it and the herd, and a
sale the invoice could not be drafted for is refused where it is agreed, with a
sentence the manager can act on.
"""

import unittest
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import culling, sale_invoice
from upande_livestock.serverscripts.culling.approve_cull import approve_cull
from upande_livestock.serverscripts.culling.raise_cull import raise_cull
from upande_livestock.serverscripts.culling.vet_verdict import vet_verdict
from upande_livestock.serverscripts.disposal.buyer_search import buyer_search
from upande_livestock.serverscripts.disposal.create_buyer import create_buyer
from upande_livestock.serverscripts.disposal.sale_terms import sale_terms
from upande_livestock.serverscripts.disposal.sell_livestock_asset import _sell_livestock_asset
from upande_livestock.serverscripts.tests.test_culling import _tidy
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge


class _Base(IntegrationTestCase):
	tag = "ZZ SALE TERMS COW"

	def setUp(self):
		for doctype, name in (("Item", "herd"), ("Asset Category", "Herd")):
			if not frappe.db.exists(doctype, name):
				raise unittest.SkipTest(f"{doctype} {name} not on this site")
		self.asset = frappe.db.get_value("Asset", {"asset_category": "Herd", "docstatus": 1,
		                                           "status": "Submitted"}, "name")
		if not self.asset:
			raise unittest.SkipTest("no submitted Herd asset on this site")
		# An endpoint that fails rolls the transaction back, which a savepoint would not
		# survive, so this cleans up by name instead and commits as the cull tests do.
		_tidy(self.tag)
		_make_cow(self.tag)
		frappe.db.set_value("Animal", self.tag, {"asset_link": self.asset, "is_capitalised": 1,
		                                         "last_weight_kg": 420})
		self.addCleanup(_tidy, self.tag)
		self.made = []
		self.addCleanup(self.remove_buyers)
		self.company = frappe.db.get_value("Asset", self.asset, "company")
		cur = frappe.get_cached_value("Company", self.company, "default_currency")
		was = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		if not was:
			pl = frappe.get_doc({"doctype": "Price List", "price_list_name": "ZZ ST PL " + frappe.generate_hash(length=5),
			                     "selling": 1, "currency": cur}).insert(ignore_permissions=True)
			frappe.db.set_single_value("Selling Settings", "selling_price_list", pl.name)
			self.addCleanup(self.drop_price_list, pl.name)
		was_farm = frappe.db.get_single_value("Livestock Settings", "custom_disposal_farm")
		self.addCleanup(lambda: (frappe.db.set_single_value("Livestock Settings", "custom_disposal_farm", was_farm),
		                         frappe.db.commit()))
		self.farm = frappe.db.get_value("Farm", {}, "name") if frappe.db.exists("DocType", "Farm") else None
		if frappe.get_meta("Sales Invoice").has_field("custom_farm") and not self.farm:
			raise unittest.SkipTest("Sales Invoice needs a Farm and none exists")
		if self.farm:
			frappe.db.set_single_value("Livestock Settings", "custom_disposal_farm", self.farm)
		if not sale_invoice.receivable_account(None, self.company):
			raise unittest.SkipTest("no receivable account to bill to")

	def buyer(self, name="ZZ Buyer", **extra):
		got = create_buyer({"customer_name": name + " " + frappe.generate_hash(length=5),
		                    "phone": "712345678", **extra})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.made.append(got["name"])
		return got["name"]

	def remove_buyers(self):
		for name in self.made:
			for si in frappe.get_all("Sales Invoice", filters={"customer": name}, pluck="name"):
				frappe.delete_doc("Sales Invoice", si, force=True, ignore_permissions=True)
			for c in frappe.get_all("Dynamic Link", filters={"link_doctype": "Customer", "link_name": name,
			                                                 "parenttype": "Contact"}, pluck="parent"):
				frappe.delete_doc("Contact", c, force=True, ignore_permissions=True)
			frappe.delete_doc("Customer", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def drop_price_list(self, name):
		frappe.db.set_single_value("Selling Settings", "selling_price_list", None)
		frappe.delete_doc("Price List", name, force=True, ignore_permissions=True)
		frappe.db.commit()


class TestCreateBuyer(_Base):
	def test_a_new_buyer_carries_what_the_books_need(self):
		name = self.buyer(tax_id="a123456789b", payment_terms="0 days")
		c = frappe.get_doc("Customer", name)
		self.assertEqual(c.tax_id, "A123456789B")
		self.assertEqual(c.mobile_no, "0712345678")
		self.assertEqual(c.default_currency, sale_invoice.company_currency(self.company))
		self.assertTrue(c.default_price_list or not frappe.db.get_single_value("Selling Settings", "selling_price_list"))
		self.assertTrue(c.customer_primary_contact)
		self.assertTrue([r for r in c.accounts if r.company == self.company])

	def test_the_same_name_gives_the_buyer_back_rather_than_a_copy(self):
		name = self.buyer()
		again = create_buyer({"customer_name": frappe.db.get_value("Customer", name, "customer_name"), "phone": "0700000001"})
		self.assertEqual(again["name"], name)
		self.assertTrue(again["existing"])

	def test_a_malformed_pin_or_no_phone_is_refused(self):
		bad = create_buyer({"customer_name": "ZZ Bad Pin", "phone": "0712345678", "tax_id": "12345"})
		self.assertIn("KRA PIN", bad["error"])
		none = create_buyer({"customer_name": "ZZ No Phone"})
		self.assertIn("phone", none["error"].lower())

	def test_a_phone_in_any_notation_gets_its_leading_zero(self):
		for raw in ("+254 712 345 678", "254712345678", "712345678", "0712345678"):
			self.assertEqual(sale_invoice.phone(raw), "0712345678")

	def test_search_finds_the_buyer_by_phone_and_name(self):
		name = self.buyer(name="ZZ Findable")
		self.assertIn(name, [b["name"] for b in buyer_search({"term": "Findable"})["buyers"]])
		self.assertIn(name, [b["name"] for b in buyer_search({"term": "0712345678"})["buyers"]])


class TestTheDraftIsComplete(_Base):
	def test_the_invoice_carries_every_detail_the_form_settled(self):
		buyer = self.buyer(payment_terms="0 days")
		got = _sell_livestock_asset(animal=self.tag, customer=buyer, selling_amount=90000, posting_date=today())
		si = frappe.get_doc("Sales Invoice", got["sales_invoice"])
		self.assertEqual(si.docstatus, 0)
		self.assertEqual(si.customer, buyer)
		self.assertEqual(si.company, self.company)
		self.assertTrue(si.debit_to)
		self.assertEqual(si.debit_to, sale_invoice.receivable_account(buyer, self.company))
		self.assertTrue(si.items[0].cost_center)
		self.assertEqual(si.items[0].rate, 90000)
		self.assertEqual(str(si.due_date), today())
		self.assertEqual(si.tax_id or None, frappe.db.get_value("Customer", buyer, "tax_id"))
		if si.meta.has_field("custom_sales_type_code"):
			self.assertEqual((si.custom_sales_type_code, si.custom_receipt_type_code, si.custom_payment_type_code),
			                 ("N", "S", "01"))
		if self.farm and si.meta.has_field("custom_farm"):
			self.assertEqual(si.custom_farm, self.farm)
		self.assertIn("Livestock sale", si.remarks)

	def test_credit_terms_move_the_due_date_and_the_payment_type(self):
		tpl = frappe.db.get_value("Payment Terms Template", {"name": ["like", "%14%"]}, "name") \
			or frappe.db.get_value("Payment Terms Template", {}, "name")
		if not tpl or not frappe.db.get_value("Payment Terms Template Detail", {"parent": tpl, "credit_days": [">", 0]}):
			raise unittest.SkipTest("no payment terms with credit days on this site")
		buyer = self.buyer(payment_terms=tpl)
		terms = sale_invoice.resolve_terms(self.tag, buyer, 50000, today())
		self.assertGreater(terms["due_date"], today())
		self.assertEqual(terms["payment_type_code"], "02")

	def test_mpesa_buyers_need_no_mode_of_payment_and_a_chosen_one_sets_the_code(self):
		buyer = self.buyer()
		blank = sale_invoice.resolve_terms(self.tag, buyer, 50000, today())
		self.assertIsNone(blank["mode_of_payment"])
		mode = frappe.db.get_value("Mode of Payment", {"type": "Phone"}, "name") or frappe.db.get_value("Mode of Payment", {}, "name")
		if mode:
			chosen = sale_invoice.resolve_terms(self.tag, buyer, 50000, today(), mode_of_payment=mode)
			kind = frappe.db.get_value("Mode of Payment", mode, "type")
			self.assertEqual(chosen["payment_type_code"], "06" if kind == "Phone" else chosen["payment_type_code"])

	def test_per_kg_is_the_rate_times_her_last_weight(self):
		buyer = self.buyer()
		terms = sale_invoice.resolve_terms(self.tag, buyer, None, today(), price_basis="Per kg", rate=250)
		self.assertEqual(terms["weight_kg"], 420)
		self.assertEqual(terms["amount"], 105000)

	def test_the_cost_centre_comes_from_her_herd_first(self):
		cc = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 0}, "name")
		herd = frappe.db.get_value("Herds", {}, "name")
		if not (cc and herd):
			raise unittest.SkipTest("no herd or cost centre here")
		frappe.db.set_value("Herds", herd, "cost_center", cc)
		frappe.db.set_value("Animal", self.tag, "current_herd", herd)
		terms = sale_invoice.resolve_terms(self.tag, self.buyer(), 1000, today())
		self.assertEqual(terms["cost_center"], cc)


class TestWhatIsMissingIsSaid(_Base):
	def test_no_buyer_is_said_plainly(self):
		terms = sale_invoice.resolve_terms(self.tag, None, 1000, today())
		self.assertIn("Choose the buyer", sale_invoice.missing(terms)[0])

	def test_a_disabled_customer_is_refused(self):
		buyer = self.buyer()
		frappe.db.set_value("Customer", buyer, "disabled", 1)
		terms = sale_invoice.resolve_terms(self.tag, buyer, 1000, today())
		self.assertTrue(any("disabled" in m for m in sale_invoice.missing(terms)))

	def test_a_foreign_billing_currency_is_refused(self):
		buyer = self.buyer()
		other = "USD" if sale_invoice.company_currency(self.company) != "USD" else "EUR"
		frappe.db.set_value("Customer", buyer, "default_currency", other)
		terms = sale_invoice.resolve_terms(self.tag, buyer, 1000, today())
		self.assertTrue(any(other in m for m in sale_invoice.missing(terms)))

	def test_no_receivable_account_is_refused_with_the_customer_named(self):
		buyer = self.buyer()
		with mock.patch.object(sale_invoice, "receivable_account", return_value=None):
			terms = sale_invoice.resolve_terms(self.tag, buyer, 1000, today())
		issues = sale_invoice.missing(terms)
		self.assertTrue(any("receivable account" in m and buyer in m for m in issues), issues)
		with self.assertRaises(frappe.ValidationError):
			sale_invoice.assert_ready(terms)

	def test_a_zero_price_is_refused(self):
		terms = sale_invoice.resolve_terms(self.tag, self.buyer(), 0, today())
		self.assertTrue(any("price" in m for m in sale_invoice.missing(terms)))


class TestTheSaleFormEndpoint(_Base):
	def test_the_preview_has_the_buyer_the_lines_and_nothing_missing(self):
		buyer = self.buyer(tax_id="P051234567Z")
		got = sale_terms({"animal": self.tag, "customer": buyer, "sale_price": 90000, "posting_date": today()})
		self.assertTrue(got["ok"], got.get("error"))
		self.assertEqual(got["missing"], [])
		self.assertEqual(got["customer"]["tax_id"], "P051234567Z")
		self.assertTrue(got["customer"]["receivable"])
		line = got["lines"][0]
		self.assertEqual((line["qty"], line["rate"], line["amount"]), (1, 90000, 90000))
		self.assertEqual(line["asset"], self.asset)
		self.assertEqual(got["grand_total"], 90000)
		# a preview saves nothing
		self.assertFalse(frappe.db.exists("Sales Invoice", {"customer": buyer}))

	def test_the_preview_reports_what_is_missing_instead_of_failing(self):
		got = sale_terms({"animal": self.tag, "customer": self.buyer(), "sale_price": 0})
		self.assertTrue(got["ok"])
		self.assertTrue(got["missing"])
		self.assertEqual(got["lines"], [])


class TestApprovalSettlesTheTerms(_Base):
	def _case(self):
		case = raise_cull({"animal": self.tag, "flow": culling.SALE})
		self.assertIn("name", case, case)
		vet_verdict({"case": case["name"], "verdict": "Fit for sale"})
		frappe.db.commit()  # a refused approval rolls the request back; the case must outlive it
		return case["name"]

	def test_a_typed_name_is_no_longer_a_buyer(self):
		got = approve_cull({"case": self._case(), "sale_price": 50000, "buyer_name": "Juma"})
		self.assertIn("Choose the buyer", got["error"])

	def test_approval_stores_the_resolved_terms_on_the_case(self):
		buyer = self.buyer()
		case = self._case()
		got = approve_cull({"case": case, "sale_price": 75000, "customer": buyer})
		self.assertTrue(got.get("ok"), got.get("error"))
		doc = frappe.get_doc("Livestock Disposal", case)
		self.assertEqual(doc.customer, buyer)
		self.assertEqual(doc.sale_price, 75000)
		self.assertEqual(doc.sale_company, self.company)
		self.assertTrue(doc.sale_debit_to)
		self.assertTrue(doc.sale_cost_center)
		self.assertEqual(doc.buyer_contact, "0712345678")

	def test_an_incomplete_sale_is_not_approved(self):
		buyer = self.buyer()
		frappe.db.set_value("Customer", buyer, "disabled", 1)
		case = self._case()
		got = approve_cull({"case": case, "sale_price": 75000, "customer": buyer})
		self.assertIn("disabled", got["error"])
		self.assertEqual(frappe.db.get_value("Livestock Disposal", case, "custom_review_status"), culling.AWAITING_APPROVAL)

	def test_per_kg_prices_the_sale_from_the_weight(self):
		case = self._case()
		got = approve_cull({"case": case, "customer": self.buyer(), "price_basis": "Per kg", "rate": 200, "weight_kg": 400})
		self.assertTrue(got.get("ok"), got.get("error"))
		doc = frappe.get_doc("Livestock Disposal", case)
		self.assertEqual(doc.sale_price, 80000)
		self.assertEqual(doc.sale_price_basis, "Per kg")
