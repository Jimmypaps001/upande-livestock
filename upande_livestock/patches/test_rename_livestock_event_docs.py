# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.rename_livestock_event_docs import NEW_NAME_RE, build_name, execute


class TestRenameLivestockEventDocs(IntegrationTestCase):
	def test_build_name_slugifies_and_uses_the_event_year(self):
		self.assertRegex(build_name("Pregnancy Diagnosis", "2025-06-01"), r"^PREGNANCY-DIAGNOSIS-2025-\d{5}$")

	def test_new_name_pattern_accepts_migrated_names_and_rejects_old_ones(self):
		self.assertTrue(NEW_NAME_RE.match("VACCINATION-2026-00001"))
		self.assertTrue(NEW_NAME_RE.match("HEAT-DETECTION-2024-00012"))
		self.assertFalse(NEW_NAME_RE.match("ABIGEAL-129257-Vaccination-1736472"))

	def test_all_events_carry_new_style_names_after_the_patch(self):
		execute()
		stale = frappe.db.sql_list(
			"SELECT name FROM `tabLivestock Event` WHERE name NOT REGEXP '^[A-Z0-9-]+-[0-9]{4}-[0-9]{5}$'"
		)
		self.assertEqual(stale, [])

	def test_no_event_type_is_left_dangling(self):
		execute()
		dangling = frappe.db.sql_list(
			"""SELECT e.event_type FROM `tabLivestock Event` e
			   LEFT JOIN `tabLivestock Event Type` t ON t.name = e.event_type
			   WHERE t.name IS NULL"""
		)
		self.assertEqual(dangling, [])

	def test_patch_is_idempotent(self):
		execute()
		before = frappe.db.count("Livestock Event")
		names_before = set(frappe.db.sql_list("SELECT name FROM `tabLivestock Event`"))
		execute()
		self.assertEqual(frappe.db.count("Livestock Event"), before)
		self.assertEqual(set(frappe.db.sql_list("SELECT name FROM `tabLivestock Event`")), names_before)

	def test_execute_renames_a_legacy_named_row_and_preserves_its_data(self):
		"""Drive execute() against a real old-style-named row, not just assert
		about already-migrated data.

		By the time this test module runs against a live site, every row in
		tabLivestock Event may already carry a new-style name (the patch has run
		for real), which would let test_all_events_carry_new_style_names... and
		friends pass even against a stubbed `execute(): pass`. This test creates
		its own throwaway row, forces a legacy-style name onto it with a direct
		SQL UPDATE (exactly the shape real historic data had:
		{animal}-{event_type}-{seq}), and proves execute() actually renames it —
		via build_name() — while the row's data survives the rename intact.
		"""
		animal = frappe.db.get_value("Animal", {}, "name")
		operator = frappe.db.get_value("Employee", {}, "name")
		marker = f"rename-execute-test-{frappe.generate_hash(length=8)}"

		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": animal,
				"event_type": "Feeding",
				"event_date": "2025-06-01",
				"operator": operator,
				"remarks": marker,
			}
		).insert()

		def _cleanup():
			# Look the row up by its remarks marker rather than any specific name:
			# it may still carry the name insert() gave it (if the UPDATE below
			# never ran or never committed), the forced legacy name, or the name
			# execute() renamed it to. Safe (a no-op) if the row was never created.
			current_name = frappe.db.get_value("Livestock Event", {"remarks": marker}, "name")
			if current_name:
				frappe.db.delete("Livestock Event", {"name": current_name})
				frappe.db.commit()

		# Registered immediately after insert() returns — before the UPDATE/commit
		# below, which could itself raise — so this throwaway row (against a real
		# production Animal) can never survive an error in this test uncleaned.
		self.addCleanup(_cleanup)

		legacy_name = f"{animal}-Feeding-{frappe.generate_hash(length=6)}"
		frappe.db.sql("UPDATE `tabLivestock Event` SET name = %s WHERE name = %s", (legacy_name, doc.name))
		frappe.db.commit()

		self.assertTrue(frappe.db.exists("Livestock Event", legacy_name))
		self.assertFalse(NEW_NAME_RE.match(legacy_name))

		execute()

		expected_name = build_name("Feeding", "2025-06-01")
		# The counter portion of build_name() is a live sequence, so compare
		# everything except the trailing #####.
		self.assertEqual(expected_name.rsplit("-", 1)[0], "FEEDING-2025")

		self.assertFalse(frappe.db.exists("Livestock Event", legacy_name))
		new_name = frappe.db.get_value("Livestock Event", {"remarks": marker}, "name")
		self.assertIsNotNone(new_name, "renamed row not found by its remarks marker")
		self.assertRegex(new_name, r"^FEEDING-2025-\d{5}$")
		self.assertTrue(NEW_NAME_RE.match(new_name))

		# The rename must not have touched anything but the name: the row's
		# other data must have made the trip intact.
		renamed = frappe.get_doc("Livestock Event", new_name)
		self.assertEqual(renamed.animal, animal)
		self.assertEqual(renamed.remarks, marker)
		self.assertEqual(str(renamed.event_date), "2025-06-01")
