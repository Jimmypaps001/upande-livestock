# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.backfill_animal_disabled import RETIRED_STATUSES, execute


class TestBackfillAnimalDisabled(IntegrationTestCase):
	def _animal(self, tag, status):
		if frappe.db.exists("Animal", tag):
			frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": tag,
				"burn_name": tag,
				"sex": "Female",
				"status": status,
			}
		).insert()
		self.addCleanup(self._purge, tag)
		# Force disabled back to 0 so the patch has something to do — inserting with a
		# retired status does not itself set it.
		frappe.db.set_value("Animal", tag, "disabled", 0, update_modified=False)
		frappe.db.commit()
		return doc

	def _purge(self, tag):
		if frappe.db.exists("Animal", tag):
			frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_retired_statuses_list_matches_the_animal_select(self):
		options = frappe.get_meta("Animal").get_field("status").options.split("\n")
		for status in RETIRED_STATUSES:
			self.assertIn(status, options, f"{status} is not a valid Animal status")

	def test_backfill_disables_a_retired_animal(self):
		self._animal("TEST-BACKFILL-DEAD", "Dead")
		self.assertEqual(frappe.db.get_value("Animal", "TEST-BACKFILL-DEAD", "disabled"), 0)
		execute()
		self.assertEqual(frappe.db.get_value("Animal", "TEST-BACKFILL-DEAD", "disabled"), 1)

	def test_backfill_leaves_an_active_animal_alone(self):
		self._animal("TEST-BACKFILL-ACTIVE", "Active")
		execute()
		self.assertEqual(frappe.db.get_value("Animal", "TEST-BACKFILL-ACTIVE", "disabled"), 0)

	def test_backfill_is_idempotent(self):
		self._animal("TEST-BACKFILL-SOLD", "Sold")
		execute()
		execute()
		self.assertEqual(frappe.db.get_value("Animal", "TEST-BACKFILL-SOLD", "disabled"), 1)
