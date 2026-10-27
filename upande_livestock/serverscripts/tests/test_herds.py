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


class TestUpdateASubmittedHerd(IntegrationTestCase):
	"""create_herd submits the herds it makes, so real herds are docstatus 1."""

	def setUp(self):
		isolate(self)
		clear_bands()

	def _created(self, name, **extra):
		from upande_livestock.serverscripts.herds.create_herd import create_herd

		out = create_herd({"herd_name": name, "herd_class": "Fattening", "min_weight_kg": 150,
		                   "max_weight_kg": 250, **extra})
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(frappe.db.get_value("Herds", name, "docstatus"), 1)
		return name

	def test_update_herd_edits_a_herd_made_by_create_herd(self):
		name = self._created("ZZ Sub A")
		out = update_herd(name, max_weight_kg=300, target_adg_kg=1.1, weigh_monthly=0)
		self.assertTrue(out.get("ok"), out)
		self.assertEqual((out["max_weight_kg"], out["target_adg_kg"], out["weigh_monthly"]), (300, 1.1, 0))

	def test_a_livestock_manager_may_edit_a_submitted_herd(self):
		name = self._created("ZZ Sub M")
		user = "zz.herd.manager@example.com"
		frappe.get_doc({"doctype": "User", "email": user, "first_name": "ZZ", "send_welcome_email": 0,
		                "roles": [{"role": "Livestock Manager"}]}).insert(ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(user)
		out = update_herd(name, max_weight_kg=260)
		self.assertTrue(out.get("ok"), out)

	def test_band_rules_still_apply_to_a_submitted_herd(self):
		a = self._created("ZZ Sub A")
		make_herd("ZZ Sub B", "Fattening", 250, 350)
		out = update_herd(a, max_weight_kg=300)
		self.assertIn("overlap", out["error"].lower())


class TestLeavingTheLadderKeepsItWhole(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		clear_bands()
		self.a = make_herd("ZZ Lad A", "Fattening", 100, 200)
		self.b = make_herd("ZZ Lad B", "Fattening", 200, 300)
		self.c = make_herd("ZZ Lad C", "Fattening", 300, 0)

	def test_changing_a_middle_band_away_from_fattening_is_refused(self):
		self.b.herd_class = "Other"
		with self.assertRaises(frappe.ValidationError):
			self.b.save()

	def test_deleting_a_middle_band_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Herds", self.b.name, ignore_permissions=True)

	def test_the_ends_may_leave(self):
		frappe.delete_doc("Herds", self.a.name, ignore_permissions=True)
		self.c.herd_class = "Other"
		self.c.save()
