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
		# Assert the positive naming contract, not just the tag's absence: a
		# fallback hash name (autoname() missing/no-op) also never contains the
		# animal tag, so that alone would pass without exercising autoname() at
		# all. Only a real TYPE-YEAR-##### name for this event's type satisfies
		# both.
		self.assertRegex(doc.name, r"^FEEDING-2026-\d{5}$")
		self.assertNotIn(self.animal, doc.name)

	def test_title_field_is_event_type(self):
		self.assertEqual(frappe.get_meta("Livestock Event").title_field, "event_type")

	def test_event_type_is_a_link_to_the_master(self):
		field = frappe.get_meta("Livestock Event").get_field("event_type")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Livestock Event Type")

	def _cleanup_by_remarks(self, marker):
		"""Register a cleanup that deletes any Livestock Event carrying `marker`
		in its remarks, whatever name it ended up with (hash-named, TYPE-YEAR-,
		or never created at all).

		Used by tests that expect insert() to raise: if the guard they're testing
		is ever removed or broken, insert() succeeds instead of raising, and
		without this the resulting row — hash-named, since it never reached a
		working autoname() — would have no name to clean up by and would be left
		behind in the live table forever. This is not speculative: exactly this
		happened during development when autoname() was temporarily stubbed to
		verify these tests actually catch its absence.
		"""
		self.addCleanup(
			lambda: (frappe.db.delete("Livestock Event", {"remarks": marker}), frappe.db.commit())
		)

	def test_unknown_event_type_is_rejected(self):
		marker = f"unknown-event-type-test-{frappe.generate_hash(length=8)}"
		self._cleanup_by_remarks(marker)
		with self.assertRaises(frappe.exceptions.LinkValidationError):
			make_event("Not A Real Type", self.animal, "2026-03-04", remarks=marker)

	def test_missing_event_type_throws_a_clear_message(self):
		marker = f"missing-event-type-test-{frappe.generate_hash(length=8)}"
		self._cleanup_by_remarks(marker)
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_date": "2026-03-04",
				"remarks": marker,
			}
		)
		# event_type's own reqd=1 would raise a MandatoryError (also a
		# ValidationError) later in the insert flow if autoname()'s own guard
		# were ever deleted, which would still satisfy a bare
		# assertRaises(ValidationError) without that guard existing at all.
		# Bypass mandatory validation so this test proves the guard itself
		# fires, by asserting on the exact message autoname() raises.
		doc.flags.ignore_mandatory = True
		with self.assertRaisesRegex(frappe.exceptions.ValidationError, "Event Type is required"):
			doc.insert()


class TestLivestockEventAccountingRemoved(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		self.animal = make_animal("TEST-NOACCT-1").name
		self.addCleanup(_delete_and_commit, "Animal", self.animal)

	def test_accounting_fields_are_gone(self):
		meta = frappe.get_meta("Livestock Event")
		for fieldname in (
			"custom_activity_cost",
			"custom_expense_account",
			"custom_cost_center",
			"custom_journal_entry",
		):
			self.assertIsNone(meta.get_field(fieldname), f"{fieldname} still on the doctype")

	def test_submitting_creates_no_journal_entry(self):
		before = frappe.db.count("Journal Entry")
		doc = make_event(
			"Feeding", self.animal, "2026-03-04", operator=frappe.db.get_value("Employee", {}, "name")
		)
		# make_event() calls insert() itself, so register cleanup immediately
		# after it returns — before submit() and the assertion below — the same
		# ordering TestLivestockEventNaming.make_event() uses, so a failure here
		# still leaves the row scheduled for deletion instead of leaking it into
		# the live 576-row table. frappe.db.delete() is a raw SQL delete, so it
		# removes the row regardless of docstatus once this submits it.
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		doc.submit()
		self.assertEqual(frappe.db.count("Journal Entry"), before)

	def test_setting_is_gone_from_livestock_settings(self):
		self.assertIsNone(frappe.get_meta("Livestock Settings").get_field("custom_auto_create_journal_entry"))


class TestLivestockEventBirth(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		if not frappe.db.exists("Herds", "TEST-BIRTH-CALVES"):
			frappe.get_doc(
				{
					"doctype": "Herds",
					"herd_name": "TEST-BIRTH-CALVES",
					"min_age": 0,
					"max_age": 1,
					"custom_is_calf_rearing": 1,
				}
			).insert()
			self.addCleanup(_delete_and_commit, "Herds", "TEST-BIRTH-CALVES")
		self.dam = make_animal("TEST-BIRTH-DAM").name
		self.addCleanup(_delete_and_commit, "Animal", self.dam)
		self.operator = frappe.db.get_value("Employee", {}, "name")
		for tag in ("TEST-BIRTH-CALF-1", "TEST-BIRTH-CALF-2"):
			if frappe.db.exists("Animal", tag):
				frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
				frappe.db.commit()
			self.addCleanup(_delete_and_commit, "Animal", tag)

	def _birth(self, tag, sex="Female", **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Birth",
				"event_date": "2026-06-01",
				"operator": self.operator,
				"dam": self.dam,
				"calf_tag_number": tag,
				"calf_sex": sex,
				**kwargs,
			}
		)
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		return doc

	def test_birth_creates_the_calf_in_the_calf_herd(self):
		event = self._birth("TEST-BIRTH-CALF-1")
		self.assertEqual(event.animal, "TEST-BIRTH-CALF-1")
		calf = frappe.get_doc("Animal", event.animal)
		self.assertEqual(calf.current_herd, "TEST-BIRTH-CALVES")
		self.assertEqual(calf.dam, self.dam)
		self.assertEqual(calf.repro_status, "Calf")

	def test_birth_bumps_the_herd_count(self):
		self._birth("TEST-BIRTH-CALF-1")
		expected = frappe.db.count("Animal", {"current_herd": "TEST-BIRTH-CALVES", "docstatus": ["!=", 2]})
		self.assertEqual(frappe.db.get_value("Herds", "TEST-BIRTH-CALVES", "number_of_animals"), expected)

	def test_duplicate_calf_tag_throws(self):
		self._birth("TEST-BIRTH-CALF-1")
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._birth("TEST-BIRTH-CALF-1")

	def test_stillborn_birth_creates_no_animal(self):
		before = frappe.db.count("Animal")
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Birth",
				"event_date": "2026-06-02",
				"operator": self.operator,
				"dam": self.dam,
				"is_stillborn": 1,
			}
		)
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		self.assertFalse(doc.animal)
		self.assertEqual(frappe.db.count("Animal"), before)

	def test_resubmitting_does_not_double_create(self):
		event = self._birth("TEST-BIRTH-CALF-1")
		event.submit()
		event.reload()
		self.assertEqual(frappe.db.count("Animal", {"tag_number": "TEST-BIRTH-CALF-1"}), 1)


class TestLivestockEventAnimalMandatory(IntegrationTestCase):
	"""animal carries mandatory_depends_on in the JSON, which is desk-UI-only in
	Frappe 16 (see LivestockEvent.validate()'s ANIMAL block). These tests exist to
	catch exactly the defect that shipped once already: removing `reqd: 1` from
	`animal` with no server-side backing let any event type through animal-less.
	"""

	def setUp(self):
		ensure_livestock_event_types()
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def _cleanup_by_remarks(self, marker):
		"""Same rationale as TestLivestockEventNaming._cleanup_by_remarks: if the
		guard under test is ever removed, insert() succeeds instead of raising,
		leaving a hash-named row with no other handle to clean it up by.
		"""
		self.addCleanup(
			lambda: (frappe.db.delete("Livestock Event", {"remarks": marker}), frappe.db.commit())
		)

	def test_feeding_event_with_no_animal_throws(self):
		marker = f"animal-mandatory-test-{frappe.generate_hash(length=8)}"
		self._cleanup_by_remarks(marker)
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Feeding",
				"event_date": "2026-06-03",
				"operator": self.operator,
				"remarks": marker,
			}
		)
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_stillborn_flag_does_not_exempt_a_non_birth_event(self):
		"""is_stillborn is only meaningful for Birth. A Feeding event flagged
		is_stillborn must still require an animal — the exemption is scoped to
		"this type creates animals AND is_stillborn", not a bare is_stillborn
		check, precisely so this case cannot slip through.
		"""
		marker = f"animal-mandatory-stillborn-test-{frappe.generate_hash(length=8)}"
		self._cleanup_by_remarks(marker)
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Feeding",
				"event_date": "2026-06-03",
				"operator": self.operator,
				"is_stillborn": 1,
				"remarks": marker,
			}
		)
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()
