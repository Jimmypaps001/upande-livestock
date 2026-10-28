# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Beef exits: per-kg sales, slaughter with final gain, the withdrawal warning.

Everything is built inside the test (company Mutara, a customer, the animal
sale item, an asset category) so the Sales Invoices and Asset disposals are
real postings, rolled back with the test.
"""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.disposal.record_disposal import record_disposal
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, submit_weight

COMPANY = "Mutara"


def _customer():
	return frappe.get_doc({
		"doctype": "Customer", "customer_name": "ZZ Butcher " + frappe.generate_hash(length=6),
		"customer_group": "Individual", "territory": "Kenya",
	}).insert(ignore_permissions=True).name


def _sale_item():
	"""An item priced per kg. Its stock UOM is Nos on purpose: selling it in Kg
	must not need anyone to have configured a conversion first."""
	item = frappe.get_doc({
		"doctype": "Item", "item_code": "ZZ Live Bull " + frappe.generate_hash(length=6),
		"item_group": "All Item Groups", "stock_uom": "Nos", "is_stock_item": 0,
	}).insert(ignore_permissions=True).name
	frappe.db.set_single_value("Livestock Settings", "custom_animal_sale_item", item)
	return item


def _employee():
	name = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	if name:
		return name
	return frappe.get_doc({
		"doctype": "Employee", "first_name": "ZZ Stockman", "gender": "Male", "company": COMPANY,
		"date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
	}).insert(ignore_permissions=True).name


def _capitalise(animal):
	"""Put the animal on the books as an Asset, the way a bought-in animal is."""
	tag = frappe.generate_hash(length=6)
	category = frappe.get_doc({
		"doctype": "Asset Category", "asset_category_name": "ZZ Cattle " + tag,
		"accounts": [{
			"company_name": COMPANY,
			"fixed_asset_account": "Capital Equipment - MUT",
			"accumulated_depreciation_account": "Accumulated Depreciation - MUT",
			"depreciation_expense_account": "Depreciation - MUT",
		}],
	}).insert(ignore_permissions=True)
	item = frappe.get_doc({
		"doctype": "Item", "item_code": "ZZ Asset Bull " + tag, "item_group": "All Item Groups",
		"stock_uom": "Nos", "is_stock_item": 0, "is_fixed_asset": 1,
		"asset_category": category.name,
	}).insert(ignore_permissions=True)
	location = frappe.get_doc({"doctype": "Location", "location_name": "ZZ Pen " + tag}).insert(ignore_permissions=True)
	asset = frappe.get_doc({
		"doctype": "Asset", "item_code": item.name, "asset_name": "ZZ Bull " + tag,
		"asset_category": category.name, "company": COMPANY, "location": location.name,
		"purchase_date": add_days(today(), -200), "available_for_use_date": add_days(today(), -200),
		"net_purchase_amount": 90000, "calculate_depreciation": 0,
	}).insert(ignore_permissions=True)
	asset.submit()
	frappe.db.set_value("Animal", animal, {"is_capitalised": 1, "asset_link": asset.name})
	return asset.name


class TestBeefExits(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.herd = make_herd("ZZ Exit Herd", "Fattening", min_kg=0, max_kg=900).name
		self.customer = _customer()
		self.item = _sale_item()

	def _sell(self, animal, **extra):
		got = record_disposal({
			"animal": animal, "disposal_type": "Sold", "customer": self.customer,
			"price_per_kg": 380, **extra,
		})
		self.assertTrue(got.get("ok"), got.get("error"))
		return got

	def test_sale_amount_is_weight_times_price_per_kg(self):
		a = make_animal(self.herd, 400)
		got = self._sell(a.name, exit_weight_kg=412)
		self.assertEqual(got["sale_price"], 156560.00)
		self.assertEqual(frappe.db.get_value("Livestock Disposal", got["name"], "sale_price"), 156560.00)

	def test_sale_defaults_exit_weight_to_latest_weighing(self):
		a = make_animal(self.herd, 350)
		submit_weight(a.name, 412, days_ago=0)
		got = self._sell(a.name)
		self.assertEqual(got["exit_weight_kg"], 412)
		self.assertEqual(got["sale_price"], 156560.00)

	def test_a_sale_needs_a_price_per_kg(self):
		a = make_animal(self.herd, 400)
		got = record_disposal({"animal": a.name, "disposal_type": "Sold", "customer": self.customer})
		self.assertFalse(got.get("ok"))
		self.assertIn("price per kg", got["error"])

	def test_non_capitalised_bull_can_be_sold(self):
		a = make_animal(self.herd, 412)
		got = self._sell(a.name)
		invoice = frappe.get_doc("Sales Invoice", frappe.db.get_value("Livestock Disposal", got["name"], "sales_invoice"))
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(len(invoice.items), 1)
		line = invoice.items[0]
		self.assertEqual((line.qty, line.uom, line.rate, line.item_code), (412, "Kg", 380, self.item))
		self.assertEqual(invoice.grand_total, 156560.00)
		self.assertEqual(frappe.db.get_value("Animal", a.name, ["status", "disabled"], as_dict=True),
		                 {"status": "Sold", "disabled": 1})

	def test_a_fractional_exit_weight_is_invoiced(self):
		a = make_animal(self.herd, 400)
		got = self._sell(a.name, exit_weight_kg=412.5)
		invoice = frappe.get_doc("Sales Invoice", frappe.db.get_value("Livestock Disposal", got["name"], "sales_invoice"))
		self.assertEqual((invoice.items[0].qty, invoice.grand_total), (412.5, 156750.00))

	def test_default_exit_weight_ignores_weighings_after_the_exit_date(self):
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
		a = make_animal(self.herd, 350)
		submit_weight(a.name, 412, days_ago=10)
		submit_weight(a.name, 450, days_ago=0)
		got = self._sell(a.name, disposal_date=add_days(today(), -5))
		self.assertEqual(got["exit_weight_kg"], 412)

	def test_a_cull_flow_sale_is_per_kg_for_a_never_capitalised_bull(self):
		from upande_livestock.serverscripts.common import culling
		from upande_livestock.serverscripts.culling.approve_cull import approve_cull
		from upande_livestock.serverscripts.culling.post_cull import post_cull
		from upande_livestock.serverscripts.culling.raise_cull import raise_cull

		a = make_animal(self.herd, 412)
		raised = raise_cull({"animal": a.name, "flow": culling.SALE, "customer": self.customer, "price_per_kg": 380, "operator": _employee()})
		self.assertTrue(raised.get("ok"), raised.get("error"))
		frappe.db.set_value("Livestock Disposal", raised["name"], "custom_review_status", culling.AWAITING_APPROVAL)
		approved = approve_cull({"case": raised["name"]})
		self.assertTrue(approved.get("ok"), approved.get("error"))
		self.assertEqual(frappe.db.get_value("Livestock Disposal", raised["name"], "sale_price"), 156560.00)
		frappe.db.set_value("Livestock Disposal", raised["name"], "custom_review_status", culling.APPROVED)
		posted = post_cull({"case": raised["name"], "operator": _employee()})
		self.assertTrue(posted.get("ok"), posted.get("error"))
		invoice = frappe.get_doc("Sales Invoice", posted["sales_invoice"])
		self.assertEqual((invoice.items[0].qty, invoice.items[0].uom, invoice.items[0].rate), (412, "Kg", 380))

	def test_a_cull_flow_sale_returns_the_withdrawal_warning(self):
		from upande_livestock.serverscripts.common import culling
		from upande_livestock.serverscripts.culling.approve_cull import approve_cull
		from upande_livestock.serverscripts.culling.post_cull import post_cull
		from upande_livestock.serverscripts.culling.raise_cull import raise_cull

		a = make_animal(self.herd, 412)
		raised = raise_cull({"animal": a.name, "flow": culling.SALE, "customer": self.customer, "price_per_kg": 380, "operator": _employee()})
		frappe.db.set_value("Livestock Disposal", raised["name"], "custom_review_status", culling.AWAITING_APPROVAL)
		self.assertTrue(approve_cull({"case": raised["name"]}).get("ok"))
		frappe.db.set_value("Livestock Disposal", raised["name"], "custom_review_status", culling.APPROVED)
		with patch("upande_livestock.serverscripts.common.withdrawal.slaughter_safe_date",
		           return_value=date.fromisoformat(add_days(today(), 5))):
			posted = post_cull({"case": raised["name"], "operator": _employee()})
		self.assertTrue(posted.get("ok"), posted.get("error"))
		self.assertEqual(len(posted["warnings"]), 1)
		self.assertIn("withdrawal", posted["warnings"][0])

	def test_a_desk_sale_without_a_price_per_kg_is_refused_in_validate(self):
		a = make_animal(self.herd, 412)
		doc = frappe.get_doc({"doctype": "Livestock Disposal", "animal": a.name, "disposal_type": "Sold",
		                      "disposal_date": today(), "customer": self.customer, "sale_price": 150000})
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)
		self.assertIn("price per kg", str(ctx.exception))

	def test_a_cull_sale_without_a_price_per_kg_is_refused(self):
		from upande_livestock.serverscripts.common import culling
		from upande_livestock.serverscripts.culling.raise_cull import raise_cull

		a = make_animal(self.herd, 412)
		got = raise_cull({"animal": a.name, "flow": culling.SALE, "customer": self.customer,
		                  "sale_price": 150000, "operator": _employee()})
		self.assertFalse(got.get("ok"))
		self.assertIn("price per kg", got["error"])

	def test_an_animal_with_only_a_birth_weight_has_no_exit_weight(self):
		a = make_animal(self.herd, None, date_of_birth=add_days(today(), -300), birth_weight_kg=30)
		got = record_disposal({"animal": a.name, "disposal_type": "Sold", "customer": self.customer, "price_per_kg": 380})
		self.assertFalse(got.get("ok"))
		self.assertIn("exit weight", got["error"])

	def test_a_stock_item_is_not_re_denominated_to_kg(self):
		from upande_livestock.serverscripts.disposal.sell_livestock_asset import _sell_in_kg

		stock = frappe.get_doc({"doctype": "Item", "item_code": "ZZ Stock " + frappe.generate_hash(length=6),
		                        "item_group": "All Item Groups", "stock_uom": "Nos", "is_stock_item": 1}).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError) as ctx:
			_sell_in_kg(stock.name, "Kg")
		self.assertIn("non-stock", str(ctx.exception))
		self.assertEqual(frappe.db.get_value("Item", stock.name, "stock_uom"), "Nos")

	def test_a_fresh_non_stock_item_switches_to_kg(self):
		from upande_livestock.serverscripts.disposal.sell_livestock_asset import _sell_in_kg

		self.assertEqual(frappe.db.get_value("Item", self.item, "stock_uom"), "Nos")
		_sell_in_kg(self.item, "Kg")
		self.assertEqual(frappe.db.get_value("Item", self.item, "stock_uom"), "Kg")

	def test_capitalised_bull_sale_disposes_asset(self):
		a = make_animal(self.herd, 412)
		asset = _capitalise(a.name)
		got = self._sell(a.name)
		invoice = frappe.get_doc("Sales Invoice", frappe.db.get_value("Livestock Disposal", got["name"], "sales_invoice"))
		kg = [row for row in invoice.items if row.uom == "Kg"]
		self.assertEqual([(r.qty, r.rate) for r in kg], [(412, 380)])
		self.assertEqual(invoice.grand_total, 156560.00)
		self.assertEqual(frappe.db.get_value("Asset", asset, "status"), "Sold")
		# Gain on disposal = proceeds - book value, not sales income.
		gl = frappe.get_all("GL Entry", filters={"voucher_no": invoice.name, "is_cancelled": 0},
		                    fields=["account", "debit", "credit"])
		self.assertFalse([g for g in gl if g.account == frappe.db.get_value("Company", COMPANY, "default_income_account")])
		disposal = frappe.db.get_value("Company", COMPANY, "disposal_account") or \
			frappe.db.get_value("Company", COMPANY, "gain_loss_on_asset_disposal")
		net = sum(flt(g.credit) - flt(g.debit) for g in gl if g.account == disposal)
		self.assertAlmostEqual(net, 66560.0, places=2)

	def test_slaughter_records_final_adg(self):
		a = make_animal(self.herd)
		submit_weight(a.name, 300, days_ago=100)
		submit_weight(a.name, 400, days_ago=0)
		got = record_disposal({"animal": a.name, "disposal_type": "Slaughtered"})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertAlmostEqual(got["final_adg_kg"], 1.0, places=3)
		self.assertEqual(frappe.db.get_value("Livestock Disposal", got["name"], "final_adg_kg"), 1.0)
		self.assertEqual(frappe.db.get_value("Animal", a.name, "status"), "Culled")

	def test_sale_records_final_adg_from_the_exit_weight(self):
		a = make_animal(self.herd)
		submit_weight(a.name, 300, days_ago=100)
		got = self._sell(a.name, exit_weight_kg=400)
		self.assertAlmostEqual(got["final_adg_kg"], 1.0, places=3)

	def test_withdrawal_window_warns_not_blocks(self):
		a = make_animal(self.herd, 400)
		with patch("upande_livestock.serverscripts.common.withdrawal.slaughter_safe_date",
		           return_value=date.fromisoformat(add_days(today(), 5))):
			got = record_disposal({"animal": a.name, "disposal_type": "Slaughtered"})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(frappe.db.get_value("Animal", a.name, "disabled"), 1)
		self.assertEqual(len(got["warnings"]), 1)
		self.assertIn("withdrawal", got["warnings"][0])

	def test_no_warning_once_the_withdrawal_has_passed(self):
		a = make_animal(self.herd, 400)
		with patch("upande_livestock.serverscripts.common.withdrawal.slaughter_safe_date",
		           return_value=date.fromisoformat(add_days(today(), -1))):
			got = record_disposal({"animal": a.name, "disposal_type": "Slaughtered"})
		self.assertEqual(got["warnings"], [])

	def test_other_disposal_types_are_untouched(self):
		a = make_animal(self.herd, 400)
		got = record_disposal({"animal": a.name, "disposal_type": "Died — Disease"})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["warnings"], [])
		self.assertEqual(frappe.db.get_value("Animal", a.name, "status"), "Dead")
