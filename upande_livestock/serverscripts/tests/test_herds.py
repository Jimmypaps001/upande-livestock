# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Herd classes and weight bands: the Fattening herds must tile the weight line."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.herds.update_herd import update_herd
from upande_livestock.serverscripts.tests.beef_fixtures import clear_bands, isolate, make_herd


class TestHerdBands(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		clear_bands()

	def test_overlapping_fattening_bands_rejected(self):
		make_herd("ZZ Band A", "Fattening", 150, 250)
		with self.assertRaises(frappe.ValidationError):
			make_herd("ZZ Band B", "Fattening", 200, 300)

	def test_gap_between_bands_rejected(self):
		make_herd("ZZ Band A", "Fattening", 150, 250)
		with self.assertRaises(frappe.ValidationError):
			make_herd("ZZ Band B", "Fattening", 260, 350)

	def test_only_top_band_may_be_open_ended(self):
		make_herd("ZZ Band A", "Fattening", 150, 0)
		with self.assertRaises(frappe.ValidationError):
			make_herd("ZZ Band B", "Fattening", 200, 300)

	def test_touching_bands_and_open_top_band_are_accepted(self):
		make_herd("ZZ Band A", "Fattening", 150, 250)
		make_herd("ZZ Band B", "Fattening", 250, 0)

	def test_weigh_monthly_defaults_on_for_fattening(self):
		self.assertEqual(make_herd("ZZ Fat", "Fattening", 100, 200).weigh_monthly, 1)
		self.assertEqual(make_herd("ZZ Breed", "Breeding").weigh_monthly, 1)
		self.assertEqual(make_herd("ZZ Other", "Other").weigh_monthly, 0)

	def test_weigh_monthly_stated_off_is_kept(self):
		doc = frappe.get_doc({"doctype": "Herds", "herd_name": "ZZ Fat Off", "herd_class": "Fattening",
		                      "min_weight_kg": 100, "max_weight_kg": 200})
		doc.flags.weigh_monthly_explicit = True
		self.assertEqual(doc.insert().weigh_monthly, 0)

	def test_update_herd_changes_only_what_is_given_and_zero_clears_a_band(self):
		make_herd("ZZ Band A", "Fattening", 150, 250, target_adg_kg=0.9)
		out = update_herd("ZZ Band A", max_weight_kg=300)
		self.assertTrue(out["ok"], out)
		self.assertEqual((out["min_weight_kg"], out["max_weight_kg"], out["target_adg_kg"]), (150, 300, 0.9))
		out = update_herd("ZZ Band A", herd_class="Other", min_weight_kg=0, max_weight_kg=0)
		self.assertEqual((out["herd_class"], out["min_weight_kg"], out["max_weight_kg"]), ("Other", 0, 0))

	def test_update_herd_refuses_an_overlap_with_the_validation_message(self):
		make_herd("ZZ Band A", "Fattening", 150, 250)
		make_herd("ZZ Band B", "Fattening", 250, 350)
		out = update_herd("ZZ Band B", min_weight_kg=200)
		self.assertIn("overlap", out["error"].lower())
