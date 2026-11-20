# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""bull_economics: the arithmetic, the purpose setting, and the endpoints on real rows."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.animals import bull_economics as be
from upande_livestock.serverscripts.animals.bull_economics import (
	accumulate, bull_economics, bull_economics_bulk, days_in, net_of,
)


class TestBullArithmetic(IntegrationTestCase):
	def test_burden_since_is_the_day_the_running_cost_passes_the_value(self):
		daily = [("2026-01-03", 40), ("2026-01-01", 40), ("2026-01-02", 40)]
		total, since = accumulate(daily, 100)
		self.assertEqual(total, 120)
		self.assertEqual(since, "2026-01-03")

	def test_no_burden_while_cost_stays_under_value(self):
		self.assertEqual(accumulate([("2026-01-01", 40)], 100), (40, None))

	def test_no_value_means_no_burden_date_and_no_net(self):
		self.assertEqual(accumulate([("2026-01-01", 400)], None), (400, None))
		self.assertIsNone(net_of(None, 400))

	def test_net_is_negative_when_he_has_cost_more_than_he_is_worth(self):
		self.assertEqual(net_of(100, 120), -20)

	def test_a_day_counts_in_the_herd_he_moved_to(self):
		spells = [{"herd": "A", "from": "2026-01-01", "to": "2026-01-03"},
		          {"herd": "B", "from": "2026-01-03", "to": None}]
		costs = {"A": {"2026-01-02": 1, "2026-01-03": 9}, "B": {"2026-01-03": 2, "2026-01-04": 3}}
		got = sorted(days_in(spells, costs, "2026-01-01", "2026-01-04"))
		self.assertEqual(got, [("2026-01-02", 1), ("2026-01-03", 2), ("2026-01-04", 3)])

	def test_days_before_birth_and_after_today_are_left_out(self):
		spells = [{"herd": "A", "from": "2026-01-01", "to": None}]
		costs = {"A": {"2025-12-31": 5, "2026-01-02": 1, "2026-01-09": 7}}
		self.assertEqual(days_in(spells, costs, "2026-01-01", "2026-01-05"), [("2026-01-02", 1)])


class TestBullEconomics(IntegrationTestCase):
	def setUp(self):
		self.made = []
		frappe.db.set_single_value("Livestock Settings", "bull_purpose", "Cull for sale at birth")
		frappe.db.set_single_value("Livestock Settings", "bull_price_per_kg", 100)
		self.bull = self._animal("ZZBULL-1", "Male", last_weight_kg=50, date_of_birth=add_days(today(), -30))
		self.cow = self._animal("ZZBULL-COW", "Female")

	def _animal(self, tag, sex, **extra):
		if frappe.db.exists("Animal", tag):
			frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
		a = frappe.get_doc({"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": sex,
		                    "status": "Active", "breed": frappe.db.get_value("Breed", {}, "name"), **extra}
		                   ).insert(ignore_permissions=True)
		self.made.append(a.name)
		return a

	def tearDown(self):
		for n in reversed(self.made):
			if frappe.db.exists("Animal", n):
				frappe.delete_doc("Animal", n, force=True, ignore_permissions=True)
		frappe.db.set_single_value("Livestock Settings", "bull_price_per_kg", 0)

	def test_default_purpose_is_cull_for_sale_at_birth(self):
		frappe.db.set_single_value("Livestock Settings", "bull_purpose", "")
		self.assertEqual(be.purpose(), "Cull for sale at birth")

	def test_a_stored_purpose_is_read_back(self):
		frappe.db.set_single_value("Livestock Settings", "bull_purpose", "Fattening")
		self.assertEqual(be.purpose(), "Fattening")
		self.assertFalse(bull_economics({"animal": self.bull.name})["kept_as_cost"])

	def test_a_bull_with_no_asset_is_valued_at_price_per_kg_times_weight(self):
		r = bull_economics({"animal": self.bull.name})
		self.assertTrue(r["ok"], r)
		self.assertEqual(r["value"], {"amount": 5000.0, "source": "price_per_kg", "as_of": today()})
		self.assertTrue(r["kept_as_cost"])
		self.assertEqual(r["purpose"], "Cull for sale at birth")
		self.assertEqual(r["days_kept"], 30)

	def test_no_price_and_no_asset_gives_no_value_and_no_net(self):
		frappe.db.set_single_value("Livestock Settings", "bull_price_per_kg", 0)
		r = bull_economics({"animal": self.bull.name})
		self.assertIsNone(r["value"]["amount"])
		self.assertIsNone(r["net"])
		self.assertIsNone(r["burden_since"])

	def test_a_cow_is_not_a_bull(self):
		r = bull_economics({"animal": self.cow.name})
		self.assertIn("not a bull", r["error"])

	def test_bulk_names_the_bull_and_leaves_the_cow_out(self):
		r = bull_economics_bulk()
		self.assertTrue(r["ok"], r)
		self.assertIn(self.bull.name, r["bulls"])
		self.assertNotIn(self.cow.name, r["bulls"])
		self.assertIsNone(r["bulls"][self.bull.name]["growth"])

	def test_bulk_leaves_out_a_sold_bull_unless_asked_for_by_name(self):
		frappe.db.set_value("Animal", self.bull.name, "status", "Sold")
		self.assertNotIn(self.bull.name, bull_economics_bulk()["bulls"])
		self.assertIn(self.bull.name, bull_economics_bulk({"animals": [self.bull.name]})["bulls"])
