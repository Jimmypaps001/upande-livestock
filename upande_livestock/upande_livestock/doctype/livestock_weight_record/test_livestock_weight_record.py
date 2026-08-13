# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

# This site has no standard ERPNext test fixtures (e.g. "All Departments"), so
# following the dependency graph into Herds -> BOM -> Item -> Department blows
# up. test_livestock_event.py / test_livestock_disposal.py hit the same wall;
# mirror their fix and build the fixtures we need by hand instead.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Animal", "Herds", "Company", "Employee"]


def make_animal(tag="TEST-WEIGH-1"):
	if frappe.db.exists("Animal", tag):
		return frappe.get_doc("Animal", tag)
	return frappe.get_doc(
		{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
	).insert()


def _purge_animal(tag):
	if frappe.db.exists("Animal", tag):
		frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
	frappe.db.commit()


def _purge_weight_records(animal):
	for name in frappe.get_all("Livestock Weight Record", filters={"animal": animal}, pluck="name"):
		doc = frappe.get_doc("Livestock Weight Record", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Livestock Weight Record", name, force=True, ignore_permissions=True)
	frappe.db.commit()


class TestLivestockWeightRecord(IntegrationTestCase):
	def setUp(self):
		self.animal = make_animal().name
		# Registered first so it runs LAST (addCleanup is LIFO): weight records
		# created in a test method are children of this Animal and must be
		# deleted before it, since delete_doc(force=True) does not cascade.
		self.addCleanup(_purge_animal, self.animal)
		self.addCleanup(_purge_weight_records, self.animal)
		frappe.db.delete("Livestock Weight Record", {"animal": self.animal})
		frappe.db.commit()

	def _record(self, weight, weight_date, bcs=None, submit=True):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Weight Record",
				"animal": self.animal,
				"weight_date": weight_date,
				"weight_kg": weight,
				"bcs": bcs,
				"method": "Platform Scale",
			}
		)
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def test_naming_series_and_submittability(self):
		doc = self._record(220.0, "2026-02-01")
		self.assertRegex(doc.name, r"^WT-2026-\d{5}$")
		self.assertEqual(doc.docstatus, 1)

	def test_first_record_has_no_previous_weight(self):
		doc = self._record(220.0, "2026-02-01")
		self.assertFalse(doc.previous_weight_kg)
		self.assertFalse(doc.daily_gain_kg)
		# Strengthen against the trivial "fields default empty" pass: insert a
		# second, later-dated record and confirm IT does pick up a previous
		# weight, proving the first record's emptiness reflects "no prior
		# submitted record found" rather than the lookup never running.
		second = self._record(240.0, "2026-02-15")
		self.assertEqual(second.previous_weight_kg, 220.0)

	def test_previous_weight_and_daily_gain_are_computed(self):
		self._record(200.0, "2026-02-01")
		second = self._record(230.0, "2026-03-03")
		self.assertEqual(second.previous_weight_kg, 200.0)
		self.assertEqual(str(second.previous_weight_date), "2026-02-01")
		self.assertAlmostEqual(second.daily_gain_kg, 30.0 / 30, places=4)

	def test_same_date_record_does_not_divide_by_zero(self):
		self._record(200.0, "2026-02-01")
		second = self._record(210.0, "2026-02-01")
		self.assertEqual(second.previous_weight_kg, 200.0)
		self.assertEqual(second.daily_gain_kg, 0)

	def test_submit_writes_back_to_the_animal(self):
		self._record(245.5, "2026-04-01", bcs=3.5)
		animal = frappe.get_doc("Animal", self.animal)
		self.assertEqual(animal.last_weight_kg, 245.5)
		self.assertEqual(animal.last_bcs, 3.5)

	def test_unsubmitted_record_does_not_write_back_to_the_animal(self):
		self._record(199.0, "2026-04-01", bcs=1.0, submit=False)
		animal = frappe.get_doc("Animal", self.animal)
		self.assertNotEqual(animal.last_weight_kg, 199.0)
		self.assertNotEqual(animal.last_bcs, 1.0)

	def test_backdated_record_does_not_regress_the_snapshot(self):
		# A, then B (later-dated, submitted 2nd) correctly advances the
		# snapshot; C is backdated paperwork submitted 3rd, dated BEFORE both
		# A and B. Ordinary farm behaviour (late paperwork for an old
		# weighing) must not silently drop the animal's current weight to an
		# older, lower value.
		self._record(300.0, "2026-04-01")  # A
		self._record(320.0, "2026-05-01")  # B
		animal = frappe.get_doc("Animal", self.animal)
		self.assertEqual(animal.last_weight_kg, 320.0)

		self._record(280.0, "2026-03-01")  # C, backdated
		animal.reload()
		self.assertEqual(animal.last_weight_kg, 320.0)

	def test_snapshot_updates_when_submitted_in_chronological_order(self):
		self._record(300.0, "2026-01-01")
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "last_weight_kg"), 300.0)

		self._record(310.0, "2026-02-01")
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "last_weight_kg"), 310.0)

		self._record(320.0, "2026-03-01")
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "last_weight_kg"), 320.0)

	def test_same_date_snapshot_resolves_deterministically(self):
		# Two records dated the same day: the later-entered one (higher
		# `creation`) wins, since weight_date alone can't order them.
		self._record(300.0, "2026-06-01")
		self._record(305.0, "2026-06-01")
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "last_weight_kg"), 305.0)

	def test_cancelling_the_latest_record_moves_snapshot_back(self):
		self._record(300.0, "2026-04-01")
		later = self._record(320.0, "2026-05-01")
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "last_weight_kg"), 320.0)

		later.cancel()
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "last_weight_kg"), 300.0)

	def test_cancelling_the_only_record_leaves_the_snapshot_as_is(self):
		# With nothing submitted left, the snapshot is left untouched rather
		# than zeroed: zeroing would assert the animal weighs nothing, which
		# is never true.
		only = self._record(300.0, "2026-04-01")
		only.cancel()
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "last_weight_kg"), 300.0)

	def test_non_positive_weight_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._record(0, "2026-04-02", submit=False)

	def test_future_date_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._record(250.0, add_days(today(), 3), submit=False)

	def test_validate_runs_even_if_previous_weight_lookup_is_stubbed(self):
		# Guards against a future refactor collapsing validate() so that the
		# non-positive/future-date throws only fire from inside
		# set_previous_weight().
		with patch(
			"upande_livestock.upande_livestock.doctype.livestock_weight_record."
			"livestock_weight_record.LivestockWeightRecord.set_previous_weight",
			lambda self: None,
		):
			with self.assertRaises(frappe.exceptions.ValidationError):
				self._record(0, "2026-04-02", submit=False)
