# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import ensure_livestock_event_types

# Livestock Event links out to Animal, Herds (current_herd/new_herd), Employee
# (operator), Account (custom_expense_account), Cost Center (custom_cost_center)
# and Journal Entry (custom_journal_entry). Several of these (Herds -> BOM,
# Employee, Account, ...) pull in ERPNext test module import chains (through
# subcontracting/purchase-order/blanket-order test helpers, and
# erpnext.tests.utils's module-level BootStrapTestData) that need a "Parent
# Department: All Departments" fixture this site does not have. None of the
# tests below touch herd or accounting fields, and make_animal()/make_event()
# create the Animal and Employee values they need directly, so all of these are
# safe to drop from the auto-generated dependency walk.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Animal", "Herds", "Employee", "Account", "Cost Center", "Journal Entry"]


def make_animal(tag):
	if frappe.db.exists("Animal", tag):
		return frappe.get_doc("Animal", tag)
	return frappe.get_doc(
		{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
	).insert()


def make_event(event_type, animal, event_date, **kwargs):
	# operator is a mandatory Link to Employee on Livestock Event (pre-existing,
	# untouched by this task); default it to any Employee on the site so the
	# naming tests below, which don't care who the operator is, don't have to
	# each supply one.
	kwargs.setdefault("operator", frappe.db.get_value("Employee", {}, "name"))
	doc = frappe.get_doc(
		{
			"doctype": "Livestock Event",
			"animal": animal,
			"event_type": event_type,
			"event_date": event_date,
			**kwargs,
		}
	)
	doc.insert()
	return doc


def _delete_and_commit(doctype, name):
	"""Hard-delete and commit.

	ensure_livestock_event_types() commits (see Livestock Event Type's own
	tests), so IntegrationTestCase's single class-level rollback cannot undo
	anything created after that commit — including every Livestock Event these
	tests insert. Each row created below must therefore be cleaned up (and that
	cleanup committed) explicitly, or it is left behind in the live database
	forever, inflating tabLivestock Event's row count past 576.
	"""
	frappe.db.delete(doctype, {"name": name})
	frappe.db.commit()


class TestLivestockEventNaming(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		self.animal = make_animal("TEST-NAMING-1").name
		self.addCleanup(_delete_and_commit, "Animal", self.animal)

	def make_event(self, event_type, event_date, **kwargs):
		"""Create a Livestock Event for self.animal and register its cleanup.

		Cleanup is registered immediately after insert() returns — before the
		caller makes any assertions — so a failing assertion still leaves the
		row scheduled for deletion. insert() only ever returns after the row is
		actually written (autoname/validate run first), so there is no window
		where a row could exist without also being registered here.
		"""
		doc = make_event(event_type, self.animal, event_date, **kwargs)
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		return doc

	def test_name_is_type_year_counter(self):
		doc = self.make_event("Feeding", "2026-03-04")
		self.assertRegex(doc.name, r"^FEEDING-2026-\d{5}$")

	def test_counter_increments_within_type_and_year(self):
		first = self.make_event("Feeding", "2026-03-04")
		second = self.make_event("Feeding", "2026-03-05")
		self.assertEqual(int(second.name.split("-")[-1]), int(first.name.split("-")[-1]) + 1)

	def test_multi_word_type_is_slugified(self):
		doc = self.make_event("Heat Detection", "2026-03-04")
		self.assertRegex(doc.name, r"^HEAT-DETECTION-2026-\d{5}$")

	def test_backdated_event_files_under_its_own_year(self):
		doc = self.make_event("Feeding", "2024-11-02")
		self.assertTrue(doc.name.startswith("FEEDING-2024-"))

	def test_animal_name_is_not_in_the_document_name(self):
		doc = self.make_event("Feeding", "2026-03-04")
		self.assertNotIn(self.animal, doc.name)

	def test_title_field_is_event_type(self):
		self.assertEqual(frappe.get_meta("Livestock Event").title_field, "event_type")

	def test_event_type_is_a_link_to_the_master(self):
		field = frappe.get_meta("Livestock Event").get_field("event_type")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Livestock Event Type")

	def test_unknown_event_type_is_rejected(self):
		with self.assertRaises(frappe.exceptions.LinkValidationError):
			make_event("Not A Real Type", self.animal, "2026-03-04")

	def test_missing_event_type_throws_a_clear_message(self):
		doc = frappe.get_doc(
			{"doctype": "Livestock Event", "animal": self.animal, "event_date": "2026-03-04"}
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.insert()
