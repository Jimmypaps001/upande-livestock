# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Writing a feed line in the store's unit: molasses in Litre, hay in bales.

The pure classes need no site:
    cd sites && ../env/bin/python -m unittest \
        upande_livestock.serverscripts.tests.test_feed_units

The Integration class needs one (one run per site at a time):
    bench --site mutara.local run-tests --app upande_livestock \
        --module upande_livestock.serverscripts.tests.test_feed_units
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.feeding import _doses as DO
from upande_livestock.serverscripts.feeding import _units as UN

# ── Pure ─────────────────────────────────────────────────────────────────────


class TestKilogramHasTwoNames(unittest.TestCase):
	def test_kg_and_kilogram_are_both_kilos(self):
		for uom in ("Kg", "Kilogram", "kg", "KILOGRAM", " Kg "):
			self.assertTrue(UN.is_kg(uom), uom)
		for uom in ("Gram", "Litre", "BALE", "", None):
			self.assertFalse(UN.is_kg(uom), uom)

	def test_kilos_per_kilo_whatever_it_is_called(self):
		self.assertEqual(UN.kilos_per("Kg", "Kilogram"), 1.0)
		self.assertEqual(UN.kilos_per("Kilogram", "Kg"), 1.0)

	def test_a_kg_line_is_not_an_explicit_unit(self):
		self.assertIsNone(UN.explicit_unit({"uom": "Kg"}))
		self.assertIsNone(UN.explicit_unit({"uom": "Kilogram"}))
		self.assertIsNone(UN.explicit_unit({"uom": "Gram"}))
		self.assertEqual(UN.explicit_unit({"uom": "Litre"}), "Litre")


class TestKilosPerUnit(unittest.TestCase):
	def test_molasses_stocked_in_litre_with_a_kilogram_row(self):
		# 1 kg = 0.714 L, so 1 L = 1.4 kg.
		self.assertAlmostEqual(UN.kilos_per("Litre", "Litre", 1, 1 / 1.4), 1.4)

	def test_a_bale_of_hay_stocked_in_bales_with_a_kilogram_row(self):
		# Hay: 1 kg = 0.07 bale, so a bale is about 14.3 kg.
		self.assertAlmostEqual(UN.kilos_per("BALE", "BALE", 1, 0.07), 1 / 0.07)

	def test_a_bag_of_an_item_stocked_in_kilos(self):
		# A 50 kg bag: 50 stock units (kg) per bag.
		self.assertEqual(UN.kilos_per("Bag", "Kg", 50), 50.0)

	def test_si_mass_needs_no_table(self):
		self.assertAlmostEqual(UN.kilos_per("Gram", "Litre"), 0.001)
		self.assertEqual(UN.kilos_per("Tonne", "BALE"), 1000.0)

	def test_nothing_is_guessed(self):
		# Litre of something stocked in Litre with no kilogram row: no density.
		self.assertIsNone(UN.kilos_per("Litre", "Litre", 1, None))
		self.assertIsNone(UN.kilos_per("Bag", "BALE", None, 0.07))

	def test_unit_options_list_the_stock_unit_first_and_each_once(self):
		opts = UN.unit_options("Litre", [("Kilogram", 0.714), ("Litre", 1), ("Drum", 200)])
		self.assertEqual([o["uom"] for o in opts], ["Litre", "Kilogram", "Drum"])
		kg = {o["uom"]: o["kg"] for o in opts}
		self.assertAlmostEqual(kg["Litre"], 1 / 0.714)
		self.assertEqual(kg["Kilogram"], 1.0)
		self.assertAlmostEqual(kg["Drum"], 200 / 0.714)


class TestRecipeWeight(unittest.TestCase):
	UNITS = {"molasses": {"stock_uom": "Litre", "uoms": UN.unit_options("Litre", [("Kg", 1 / 1.4)])}}

	def test_a_litre_line_weighs_its_kilos(self):
		self.assertAlmostEqual(UN.line_kilos({"item_code": "molasses", "qty": 3, "uom": "Litre"}, self.UNITS), 4.2)

	def test_a_kilo_line_and_an_unconvertible_line_keep_their_quantity(self):
		self.assertEqual(UN.line_kilos({"item_code": "silage", "qty": 15}, self.UNITS), 15)
		self.assertEqual(UN.line_kilos({"item_code": "silage", "qty": 15, "uom": "Kg"}, self.UNITS), 15)
		self.assertEqual(UN.line_kilos({"item_code": "x", "qty": 2, "uom": "Drum"}, self.UNITS), 2)

	def test_kg_total_converts_and_leaves_doses_out(self):
		lines = [
			{"item_code": "silage", "qty": 15},
			{"item_code": "molasses", "qty": 3, "uom": "Litre"},
			{"item_code": "dv", "qty": 7, "dose_uom": "Gram"},
		]
		self.assertAlmostEqual(DO.kg_total(lines, lambda r: UN.line_kilos(r, self.UNITS)), 19.2)
		# Without a converter every line counts its quantity, as before units.
		self.assertEqual(DO.kg_total(lines), 18)

	def test_a_recipe_in_kilos_asks_for_no_units(self):
		self.assertEqual(UN.units_for_lines([{"item_code": "silage", "qty": 15, "uom": "Kilogram"}]), {})


# ── Site ─────────────────────────────────────────────────────────────────────


class IntegrationFeedUnits(IntegrationTestCase):
	def setUp(self):
		for uom in ("Litre", "Kilogram"):
			if not frappe.db.exists("UOM", uom):
				frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
		self.code = "ZZ Molasses " + frappe.generate_hash(length=6)
		frappe.get_doc({
			"doctype": "Item", "item_code": self.code, "item_name": self.code,
			"item_group": "All Item Groups", "stock_uom": "Litre", "is_stock_item": 1,
			"uoms": [{"uom": "Litre", "conversion_factor": 1}, {"uom": "Kilogram", "conversion_factor": 0.714}],
		}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	def test_feed_units_returns_each_unit_with_its_kilos(self):
		from upande_livestock.serverscripts.feeding.feed_units import feed_units

		got = feed_units(items=frappe.as_json([self.code]))
		self.assertTrue(got["ok"])
		unit = got["units"][self.code]
		self.assertEqual(unit["stock_uom"], "Litre")
		kg = {o["uom"]: o["kg"] for o in unit["uoms"]}
		self.assertAlmostEqual(kg["Litre"], 1 / 0.714, places=4)
		self.assertEqual(kg["Kilogram"], 1.0)

	def test_a_ration_line_in_litre_weighs_its_kilos(self):
		from upande_livestock.serverscripts.feeding._standing_ration import per_head_kg

		self.assertAlmostEqual(
			per_head_kg([{"item_code": self.code, "qty": 3, "uom": "Litre"}, {"item_code": "x", "qty": 10}]),
			10 + 3 / 0.714,
			places=3,
		)
