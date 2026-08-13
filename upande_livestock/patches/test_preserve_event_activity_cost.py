# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import ensure_livestock_event_types
from upande_livestock.patches.preserve_event_activity_cost import MARKER, execute


def make_animal(tag):
	if frappe.db.exists("Animal", tag):
		return frappe.get_doc("Animal", tag)
	return frappe.get_doc(
		{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
	).insert()


class TestPreserveEventActivityCost(IntegrationTestCase):
	"""Drive the patch against a throwaway costed event.

	Asserting "every costed event carries the marker" would be hollow: once the
	patch has run for real, that is permanently true and passes against a stubbed
	execute(). Each test below creates its own un-marked costed row, so a stub
	fails.

	custom_activity_cost is removed from the DocType by this task, but Frappe does
	not drop orphaned columns, so it is still writable via raw SQL — which is how
	the fixture is built.
	"""

	def setUp(self):
		ensure_livestock_event_types()
		self.animal = make_animal("TEST-COST-1").name
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def _costed_event(self, cost, remarks=None):
		"""An event with a non-zero legacy activity cost and no migration marker."""
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Feeding",
				"event_date": "2026-02-01",
				"operator": self.operator,
				"remarks": remarks,
			}
		)
		doc.insert()
		self.addCleanup(self._purge, doc.name)
		frappe.db.sql(
			"""UPDATE `tabLivestock Event`
			   SET custom_activity_cost = %(cost)s, custom_expense_account = 'TEST-EXP',
			       custom_cost_center = 'TEST-CC', custom_journal_entry = 'TEST-JE'
			   WHERE name = %(name)s""",
			{"cost": cost, "name": doc.name},
		)
		frappe.db.commit()
		return doc.name

	def _purge(self, name):
		frappe.delete_doc("Livestock Event", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _remarks(self, name):
		return frappe.db.get_value("Livestock Event", name, "remarks") or ""

	def test_marker_and_details_are_written_onto_a_costed_event(self):
		name = self._costed_event(1200)
		self.assertNotIn(MARKER, self._remarks(name))
		execute()
		remarks = self._remarks(name)
		self.assertIn(MARKER, remarks)
		self.assertIn("1,200", remarks)
		self.assertIn("TEST-EXP", remarks)
		self.assertIn("TEST-CC", remarks)
		self.assertIn("TEST-JE", remarks)

	def test_existing_remarks_are_preserved_not_overwritten(self):
		name = self._costed_event(50, remarks="Original operator note")
		execute()
		remarks = self._remarks(name)
		self.assertIn("Original operator note", remarks)
		self.assertIn(MARKER, remarks)

	def test_uncosted_event_is_left_alone(self):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Feeding",
				"event_date": "2026-02-02",
				"operator": self.operator,
				"remarks": "no cost here",
			}
		)
		doc.insert()
		self.addCleanup(self._purge, doc.name)
		frappe.db.commit()
		execute()
		self.assertEqual(self._remarks(doc.name), "no cost here")

	def test_patch_is_idempotent_on_a_row_it_already_marked(self):
		name = self._costed_event(75)
		execute()
		once = self._remarks(name)
		execute()
		self.assertEqual(self._remarks(name), once)
		self.assertEqual(once.count(MARKER), 1)
