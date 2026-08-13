# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import SEED_EVENT_TYPES, ensure_livestock_event_types


class TestLivestockEventType(IntegrationTestCase):
	@staticmethod
	def _delete_and_commit(doctype, name):
		"""Hard-delete and commit.

		ensure_livestock_event_types() commits, so IntegrationTestCase's single
		class-level rollback cannot undo anything it creates. Tests that create
		throwaway rows must clean up (and commit that cleanup) themselves.
		"""
		frappe.db.delete(doctype, {"name": name})
		frappe.db.commit()

	def _assert_event_count(self, expected):
		self.assertEqual(frappe.db.count("Livestock Event"), expected)

	def test_seeds_all_fifteen_types(self):
		self.assertEqual(len(SEED_EVENT_TYPES), 17)

		# Delete two already-seeded rows and prove ensure_livestock_event_types()
		# recreates them (with the right flags), rather than merely relying on
		# rows a previous test run already committed to this site. Restore via
		# addCleanup registered before the delete, so a failed assertion below
		# still leaves the site correctly seeded.
		self.addCleanup(ensure_livestock_event_types)
		frappe.db.delete("Livestock Event Type", {"name": ["in", ["Feeding", "Birth"]]})
		frappe.db.commit()
		self.assertFalse(frappe.db.exists("Livestock Event Type", "Feeding"))
		self.assertFalse(frappe.db.exists("Livestock Event Type", "Birth"))

		ensure_livestock_event_types()

		for seed in SEED_EVENT_TYPES:
			self.assertTrue(frappe.db.exists("Livestock Event Type", seed["name"]), seed["name"])
		self.assertEqual(frappe.db.get_value("Livestock Event Type", "Birth", "creates_animal"), 1)
		self.assertEqual(frappe.db.get_value("Livestock Event Type", "Feeding", "creates_animal"), 0)

	def test_name_is_the_type_name(self):
		ensure_livestock_event_types()
		doc = frappe.get_doc("Livestock Event Type", "Feeding")
		self.assertEqual(doc.name, "Feeding")
		self.assertTrue(doc.is_active)

	def test_birth_creates_animal(self):
		ensure_livestock_event_types()
		self.assertTrue(frappe.db.get_value("Livestock Event Type", "Birth", "creates_animal"))
		self.assertFalse(frappe.db.get_value("Livestock Event Type", "Abortion", "creates_animal"))
		self.assertFalse(frappe.db.get_value("Livestock Event Type", "Calving", "creates_animal"))

	def test_detail_doctype_wired_for_health_types(self):
		ensure_livestock_event_types()
		self.assertEqual(
			frappe.db.get_value("Livestock Event Type", "Check Up", "detail_doctype"),
			"Livestock Diagnosis",
		)
		self.assertEqual(
			frappe.db.get_value("Livestock Event Type", "Health Case", "detail_doctype"),
			"Livestock Health Case",
		)

	def test_seeds_types_found_only_in_existing_data(self):
		# Deliberately not one of SEED_EVENT_TYPES, so the ordinary seed loop's
		# `if frappe.db.exists(...): continue` cannot accidentally satisfy this
		# test. Only the backfill (SELECT DISTINCT event_type FROM tabLivestock
		# Event) can create this record.
		synthetic_type = "ZZ Test Only Type"
		self.assertNotIn(synthetic_type, [seed["name"] for seed in SEED_EVENT_TYPES])

		baseline_event_count = frappe.db.count("Livestock Event")
		event_name = frappe.generate_hash(length=10)

		# Register cleanup before creating anything, in LIFO order, so it runs
		# even if an assertion below fails: delete the throwaway Livestock
		# Event row, delete the type the backfill created from it, then verify
		# tabLivestock Event is back to its original row count.
		self.addCleanup(self._assert_event_count, baseline_event_count)
		self.addCleanup(self._delete_and_commit, "Livestock Event Type", synthetic_type)
		self.addCleanup(self._delete_and_commit, "Livestock Event", event_name)

		# event_type is still a plain Select at this point (the Link conversion
		# is a later task), so a raw SQL insert sidesteps Select-option
		# validation entirely. `name` is the only NOT NULL column without a
		# server-side default.
		frappe.db.sql(
			"INSERT INTO `tabLivestock Event` (name, event_type) VALUES (%s, %s)",
			(event_name, synthetic_type),
		)
		self.assertEqual(frappe.db.count("Livestock Event"), baseline_event_count + 1)

		self.assertFalse(frappe.db.exists("Livestock Event Type", synthetic_type))
		ensure_livestock_event_types()
		self.assertTrue(frappe.db.exists("Livestock Event Type", synthetic_type))

	def test_is_idempotent(self):
		ensure_livestock_event_types()
		before = frappe.db.count("Livestock Event Type")
		ensure_livestock_event_types()
		self.assertEqual(frappe.db.count("Livestock Event Type"), before)
