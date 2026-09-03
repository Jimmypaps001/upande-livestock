# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.api.test_operations import _suspend_sex_routing

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
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Animal",
	"Herds",
	"Employee",
	"Account",
	"Cost Center",
	"Journal Entry",
	"Stock Entry",
	"Stock Entry Type",
	"Item",
	"Warehouse",
	"Department",
	"Livestock Drug Issue",
]


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
		_suspend_sex_routing(self)
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


class TestLivestockEventDateClearDetection(IntegrationTestCase):
	"""LivestockEvent.validate()'s EVENT DATE block (see the CLEAR-DETECTION
	comment there).

	event_date carries `"default": "Today"` in the DocType JSON, so
	Document.insert() always repopulates a blank event_date before
	validate() ever runs — a document cannot reach insert() with event_date
	genuinely blank, on any path (desk, REST, data import, mobile). A
	previous version of this check special-cased self.is_new(), which could
	therefore never fire. The only way event_date IS NULL ever reached this
	project's live data was a later SAVE that cleared an already-stored
	date — exactly what produced the 5 (now 3) NULL rows on kaitet.local.
	These tests exercise that real path.
	"""

	def setUp(self):
		ensure_livestock_event_types()
		self.animal = make_animal("TEST-EVENTDATE-1").name
		self.addCleanup(_delete_and_commit, "Animal", self.animal)
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def test_insert_with_no_event_date_gets_todays_date(self):
		"""Pins the DocType JSON's `"default": "Today"` behaviour that makes
		the old is_new() branch unreachable: if that default is ever removed
		from the JSON, this must fail loudly rather than silently reopen the
		gap it currently closes on insert.
		"""
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Feeding",
				"operator": self.operator,
			}
		)
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		self.assertEqual(str(doc.event_date), frappe.utils.today())

	def test_blanking_a_stored_event_date_on_update_throws(self):
		"""The damaging transition this check exists to block: a stored date
		cleared on an ordinary save — exactly how the duplicate Client-
		Script-era validate handlers in public/js/livestock_event.js produced
		the 5 NULL rows this project found.
		"""
		doc = make_event("Feeding", self.animal, "2026-06-10", operator=self.operator)
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		doc.event_date = None
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.save()

	def test_already_null_event_date_can_still_be_saved(self):
		"""Grandfathering, proven without touching any of the 3 real
		production Calving rows this project deliberately left NULL (no
		recoverable date — see backfill_event_date_from_twin_field.py,
		which is why those rows are never used directly in an automated
		test). Reconstructs the same state those rows are actually in: a row
		whose event_date is NULL not because it was ever accepted blank
		through validate() (impossible, per the default above) but because
		something outside the ORM's own defaulting cleared it after
		insert — a raw frappe.db.set_value here, exactly mirroring the real
		JS bug's effect. A resave that leaves event_date blank must not be
		blocked: nothing stored is being cleared by this save, since
		nothing is stored to begin with.
		"""
		doc = make_event("Feeding", self.animal, "2026-06-11", operator=self.operator)
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		frappe.db.set_value("Livestock Event", doc.name, "event_date", None, update_modified=False)
		doc.reload()
		self.assertFalse(doc.event_date)

		doc.remarks = "grandfathered-null-event-date-resave-test"
		doc.save()  # must not raise
		doc.reload()
		self.assertFalse(doc.event_date)


def _delete_animal_and_fix_herd(name):
	"""Delete an Animal and recompute its herd's true count.

	create_calf() bumps Herds.number_of_animals when the calf is created; a raw
	frappe.db.delete of the Animal row would leave that count one too high
	forever, breaking the "every Herd matches its true COUNT(*)" invariant.
	Recomputing here (rather than assuming the calf landed in the test's own
	throwaway TEST-BIRTH-CALVES herd) keeps the invariant intact even if
	resolve_calf_herd() picked a real herd instead.
	"""
	from upande_livestock.serverscripts.common.animal import recompute_herd_count

	herd = frappe.db.get_value("Animal", name, "current_herd")
	frappe.db.delete("Animal", {"name": name})
	frappe.db.commit()
	if herd:
		recompute_herd_count(herd)
		frappe.db.commit()


class TestLivestockEventMultipleBirths(IntegrationTestCase):
	"""One Calving event, N Birth events — created together for twins/triplets.

	IntegrationTestCase has no per-test rollback (see _delete_and_commit above),
	so every Calving, Birth and calf Animal these tests create is registered for
	cleanup immediately after it exists, in an order that respects the link
	graph: Birth events (which reference both the Calving, via related_calving,
	and the calf Animal, via .animal) are deleted before either of the docs they
	reference; the dam Animal (referenced by every Calving and Birth here) and
	the throwaway TEST-BIRTH-CALVES herd (referenced by every Animal's
	current_herd) are deleted last, via setUp's own addCleanup calls, which —
	being registered before any test body runs — sit at the bottom of the LIFO
	cleanup stack and so always run after every per-test cleanup above them.
	"""

	def setUp(self):
		_suspend_sex_routing(self)
		ensure_livestock_event_types()
		herd_created = not frappe.db.exists("Herds", "TEST-BIRTH-CALVES")
		if herd_created:
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
		self.dam = make_animal("TEST-TRIPLET-DAM").name
		self.addCleanup(_delete_and_commit, "Animal", self.dam)
		self.operator = frappe.db.get_value("Employee", {}, "name")
		for n in (1, 2, 3):
			tag = f"TEST-TRIPLET-{n}"
			if frappe.db.exists("Animal", tag):
				frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
				frappe.db.commit()

	def _calving(self, no_of_calves):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.dam,
				"event_type": "Calving",
				"event_date": "2026-07-01",
				"operator": self.operator,
				"custom_calving_outcome": "Live Birth",
				"custom_no_of_calves": no_of_calves,
			}
		)
		doc.flags.ignore_validate = True
		doc.insert()
		# Registered now, before any Birth event linked to this Calving exists —
		# LIFO puts this cleanup at the bottom of this family's stack, so it runs
		# only after every Birth event registered by _register_birth_family_cleanup
		# below.
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		doc.submit()
		return doc

	def _register_birth_family_cleanup(self, calving_name, created_animals):
		"""Register cleanup for the calf Animals and Birth events a
		record_calf_births() call (directly, or via record_birth) just produced.

		Call after the calving's own cleanup is already registered (by _calving,
		or explicitly for record_birth's own Calving). LIFO then runs: Birth
		events first (registered last, below), then the calf Animals, then the
		Calving.
		"""
		for animal in created_animals:
			self.addCleanup(_delete_animal_and_fix_herd, animal)
		for name in frappe.db.get_all(
			"Livestock Event",
			filters={"related_calving": calving_name, "event_type": "Birth"},
			pluck="name",
		):
			self.addCleanup(_delete_and_commit, "Livestock Event", name)

	def _confirm_pregnancy(self, service_date="2025-09-01", diagnosis_date="2025-10-05"):
		"""Create a submitted, Confirmed Service + Pregnancy Diagnosis for self.dam.

		record_birth's Calving creation (pre-existing, untouched by this task) does
		not set flags.ignore_validate, so its own validate() runs in full — including
		the "VALIDATION FOR CALVING" block that throws unless a Confirmed pregnancy
		can be found or was passed in. A bare Animal with no breeding history is not
		a realistic caller for record_birth in production (see the domain audit:
		every real Calving traces back through a confirmed Service), so tests that
		exercise record_birth directly must build that trail first, exactly as a
		real farm would.

		Cleanup order: registered here, before either doc exists, in Service-then-
		Diagnosis order, so — LIFO — Diagnosis (which links back to Service via
		related_service) is deleted first.
		"""
		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.dam,
				"event_type": "Service",
				"event_date": service_date,
				"operator": self.operator,
				"service_type": "A.I.",
				"service_date": service_date,
			}
		)
		service.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", service.name)
		service.submit()

		diagnosis = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.dam,
				"event_type": "Pregnancy Diagnosis",
				"event_date": diagnosis_date,
				"operator": self.operator,
				"related_service": service.name,
				"diagnosis_date": diagnosis_date,
				"diagnosis_result": "Confirmed",
			}
		)
		diagnosis.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", diagnosis.name)
		diagnosis.submit()
		return service.name

	def test_births_recorded_counts_linked_births(self):
		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		calving = self._calving(3)
		result = record_calf_births(
			{
				"calving": calving.name,
				"calves": [
					{"tag": "TEST-TRIPLET-1", "sex": "Female"},
					{"tag": "TEST-TRIPLET-2", "sex": "Female"},
					{"tag": "TEST-TRIPLET-3", "sex": "Male"},
				],
			}
		)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		calving.reload()
		self.assertEqual(calving.births_recorded, 3)

	def test_three_births_create_three_animals(self):
		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		calving = self._calving(3)
		result = record_calf_births(
			{
				"calving": calving.name,
				"calves": [
					{"tag": "TEST-TRIPLET-1", "sex": "Female"},
					{"tag": "TEST-TRIPLET-2", "sex": "Female"},
					{"tag": "TEST-TRIPLET-3", "sex": "Male"},
				],
			}
		)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		for n in (1, 2, 3):
			self.assertTrue(frappe.db.exists("Animal", f"TEST-TRIPLET-{n}"))

	def test_parity_increments_once_per_calving_not_per_birth(self):
		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		before = frappe.db.get_value("Animal", self.dam, "parity") or 0
		calving = self._calving(3)
		result = record_calf_births(
			{
				"calving": calving.name,
				"calves": [
					{"tag": "TEST-TRIPLET-1", "sex": "Female"},
					{"tag": "TEST-TRIPLET-2", "sex": "Female"},
					{"tag": "TEST-TRIPLET-3", "sex": "Male"},
				],
			}
		)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		after = frappe.db.get_value("Animal", self.dam, "parity") or 0
		self.assertEqual(after - before, 1)

	def test_stillborn_row_records_a_birth_without_an_animal(self):
		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		calving = self._calving(2)
		result = record_calf_births(
			{
				"calving": calving.name,
				"calves": [
					{"tag": "TEST-TRIPLET-1", "sex": "Female"},
					{"is_stillborn": 1},
				],
			}
		)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		calving.reload()
		self.assertEqual(calving.births_recorded, 2)
		self.assertEqual(len(result["created"]), 1)

	def test_count_mismatch_warns_but_does_not_block(self):
		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		calving = self._calving(3)
		result = record_calf_births(
			{"calving": calving.name, "calves": [{"tag": "TEST-TRIPLET-1", "sex": "Female"}]}
		)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		calving.reload()
		self.assertEqual(calving.births_recorded, 1)
		self.assertEqual(calving.custom_no_of_calves, 3)

	def test_birth_count_mismatch_actually_fires_a_warning(self):
		"""The warning has to live in refresh_calving_birth_count (fired from the
		Birth event's own submit), not in the Calving's on_submit: a Calving must
		already be submitted, with births_recorded still 0, before any Birth event
		can reference it, and a Birth's on_submit updates the parent via a raw
		db.set_value that never re-triggers the Calving's own on_submit — so a
		check placed only on Calving submission could never actually fire.
		Asserting only that submission succeeds (as
		test_count_mismatch_warns_but_does_not_block does) would pass even if this
		method were never called at all, so this test captures frappe.msgprint
		directly.

		This is a 1-of-3 batch — the whole batch is exactly one calf, so it
		completes (and must warn) after that single Birth. Asserting call_count
		== 1, not just "called", is what distinguishes "warned once, correctly"
		from "warned once per Birth", which would be indistinguishable from this
		batch's perspective alone;
		test_no_mismatch_warning_mid_batch_when_the_batch_completes and
		test_exactly_one_warning_for_a_1_of_3_batch below are the ones that
		actually exercise a multi-calf batch and would catch the per-calf-warning
		regression this could otherwise hide.
		"""
		from unittest.mock import patch

		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		calving = self._calving(3)
		with patch("frappe.msgprint") as mock_msgprint:
			result = record_calf_births(
				{"calving": calving.name, "calves": [{"tag": "TEST-TRIPLET-1", "sex": "Female"}]}
			)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		self.assertEqual(mock_msgprint.call_count, 1)
		messages = [str(call.args[0]) for call in mock_msgprint.call_args_list if call.args]
		self.assertTrue(
			any("3" in m and "1" in m for m in messages),
			f"Expected a mismatch warning mentioning 3 and 1, got: {messages}",
		)

	def test_no_mismatch_warning_mid_batch_when_the_batch_completes(self):
		"""A 3-of-3 batch (submitted in one record_calf_births call) must produce
		NO mismatch message at all — not one for calf 1 ("expects 3, got 1"),
		one for calf 2 ("expects 3, got 2"), and silence only once the batch
		settles at 3. Each Birth's own on_submit recounts against the calving's
		full expected total before the rest of the same request's calves have
		been inserted; without suppressing the message mid-batch (only the
		births_recorded count itself must stay unconditional), a batch that
		completes perfectly would still emit two false alarms — training staff
		to dismiss a warning that, on an actual gap, is the whole point of this
		feature.
		"""
		from unittest.mock import patch

		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		calving = self._calving(3)
		with patch("frappe.msgprint") as mock_msgprint:
			result = record_calf_births(
				{
					"calving": calving.name,
					"calves": [
						{"tag": "TEST-TRIPLET-1", "sex": "Female"},
						{"tag": "TEST-TRIPLET-2", "sex": "Female"},
						{"tag": "TEST-TRIPLET-3", "sex": "Male"},
					],
				}
			)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		self.assertEqual(mock_msgprint.call_count, 0)
		calving.reload()
		self.assertEqual(calving.births_recorded, 3)

	def test_exactly_one_warning_for_a_1_of_3_batch(self):
		"""A 1-of-3 batch (three expected, one submitted in this call) must
		produce exactly ONE mismatch message — not zero (the message must not
		be swallowed entirely by the mid-batch suppression) and not more than
		one (no double-firing).
		"""
		from unittest.mock import patch

		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		calving = self._calving(3)
		with patch("frappe.msgprint") as mock_msgprint:
			result = record_calf_births(
				{"calving": calving.name, "calves": [{"tag": "TEST-TRIPLET-1", "sex": "Female"}]}
			)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		self.assertEqual(mock_msgprint.call_count, 1)
		calving.reload()
		self.assertEqual(calving.births_recorded, 1)

	def test_single_birth_against_a_3_calf_calving_warns_immediately(self):
		"""A lone Birth event, inserted and submitted directly (not through
		record_calf_births at all — the desk-form path), must still warn right
		away: telling the operator immediately that 1 of 3 is recorded is the
		whole point when there is no batch to wait for.
		"""
		from unittest.mock import patch

		calving = self._calving(3)
		with patch("frappe.msgprint") as mock_msgprint:
			birth = frappe.get_doc(
				{
					"doctype": "Livestock Event",
					"event_type": "Birth",
					"event_date": "2026-07-01",
					"operator": self.operator,
					"dam": self.dam,
					"related_calving": calving.name,
					"calf_tag_number": "TEST-TRIPLET-1",
					"calf_sex": "Female",
				}
			)
			birth.insert()
			self.addCleanup(_delete_animal_and_fix_herd, birth.animal)
			self.addCleanup(_delete_and_commit, "Livestock Event", birth.name)
			birth.submit()
		self.assertEqual(mock_msgprint.call_count, 1)
		calving.reload()
		self.assertEqual(calving.births_recorded, 1)

	def test_cancelling_a_birth_from_a_complete_set_warns(self):
		"""Cancelling one Birth out of a complete set of 3 genuinely reopens a
		gap (2 of 3 now recorded) and must warn — cancellation is never part of
		a record_calf_births batch, so nothing suppresses it.
		"""
		from unittest.mock import patch

		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		calving = self._calving(3)
		result = record_calf_births(
			{
				"calving": calving.name,
				"calves": [
					{"tag": "TEST-TRIPLET-1", "sex": "Female"},
					{"tag": "TEST-TRIPLET-2", "sex": "Female"},
					{"tag": "TEST-TRIPLET-3", "sex": "Male"},
				],
			}
		)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		calving.reload()
		self.assertEqual(calving.births_recorded, 3)

		one_birth = frappe.db.get_value(
			"Livestock Event",
			{"related_calving": calving.name, "event_type": "Birth", "calf_tag_number": "TEST-TRIPLET-1"},
		)
		with patch("frappe.msgprint") as mock_msgprint:
			frappe.get_doc("Livestock Event", one_birth).cancel()
		self.assertEqual(mock_msgprint.call_count, 1)
		calving.reload()
		self.assertEqual(calving.births_recorded, 2)

	def test_created_calf_entries_carry_animal_tag_and_sex(self):
		"""result["created"][i] is the contract callers (mobile/web) read from.
		Dropping `sex` here silently gives every caller `undefined`/None instead
		of an error, so pin the exact key set as well as the value.
		"""
		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		calving = self._calving(1)
		result = record_calf_births(
			{"calving": calving.name, "calves": [{"tag": "TEST-TRIPLET-1", "sex": "Female"}]}
		)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		self.assertEqual(len(result["created"]), 1)
		# A subset check, not equality: callers read by key, so an added key is
		# harmless while a dropped one is the silent failure this guards against.
		self.assertLessEqual({"animal", "tag", "sex"}, set(result["created"][0].keys()))
		self.assertEqual(result["created"][0]["sex"], "Female")

	def test_specified_herd_wins_over_resolution(self):
		"""A per-calf herd choice (as the Livestock Operations widget already
		sends) must reach create_calf(), not be silently discarded by
		resolve_calf_herd() picking something else.
		"""
		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		alt_herd = "TEST-TRIPLET-ALT-HERD"
		if not frappe.db.exists("Herds", alt_herd):
			frappe.get_doc({"doctype": "Herds", "herd_name": alt_herd, "min_age": 50, "max_age": 60}).insert()
			self.addCleanup(_delete_and_commit, "Herds", alt_herd)

		calving = self._calving(1)
		result = record_calf_births(
			{
				"calving": calving.name,
				"calves": [{"tag": "TEST-TRIPLET-1", "sex": "Female", "herd": alt_herd}],
			}
		)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		self.assertEqual(frappe.db.get_value("Animal", "TEST-TRIPLET-1", "current_herd"), alt_herd)

	def test_empty_herd_falls_back_to_resolution(self):
		"""An empty/omitted herd must behave exactly as if none were given at
		all — resolved the same way create_calf_if_needed's own callers with no
		opinion on herd already rely on.
		"""
		from upande_livestock.serverscripts.common.animal import resolve_calf_herd
		from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births

		expected_herd = resolve_calf_herd()
		calving = self._calving(1)
		result = record_calf_births(
			{
				"calving": calving.name,
				"calves": [{"tag": "TEST-TRIPLET-1", "sex": "Female", "herd": ""}],
			}
		)
		self._register_birth_family_cleanup(calving.name, [c["animal"] for c in result["created"]])
		self.assertEqual(frappe.db.get_value("Animal", "TEST-TRIPLET-1", "current_herd"), expected_herd)

	def test_record_birth_creates_one_calving_and_n_births(self):
		"""record_birth must delegate to record_calf_births, not carry its own loop."""
		from upande_livestock.serverscripts.breeding.record_birth import record_birth

		self._confirm_pregnancy()
		result = record_birth(
			{
				"dam": self.dam,
				"operator": self.operator,
				"event_date": "2026-07-02",
				"outcome": "Live Birth",
				"calves": [
					{"name": "TEST-TRIPLET-1", "sex": "Female"},
					{"name": "TEST-TRIPLET-2", "sex": "Male"},
				],
			}
		)
		self.addCleanup(_delete_and_commit, "Livestock Event", result["name"])
		self._register_birth_family_cleanup(result["name"], [c["animal"] for c in result["calves"]])
		self.assertTrue(result["ok"])
		self.assertEqual(len(result["calves"]), 2)
		for n in (1, 2):
			self.assertEqual(frappe.db.count("Animal", {"tag_number": f"TEST-TRIPLET-{n}"}), 1)

	def test_record_birth_calves_entries_carry_animal_tag_and_sex(self):
		"""Same per-item contract as record_calf_births' own "created" list —
		record_birth returns it under the "calves" key instead.
		"""
		from upande_livestock.serverscripts.breeding.record_birth import record_birth

		self._confirm_pregnancy(service_date="2025-09-10", diagnosis_date="2025-10-14")
		result = record_birth(
			{
				"dam": self.dam,
				"operator": self.operator,
				"event_date": "2026-07-07",
				"outcome": "Live Birth",
				"calves": [{"name": "TEST-TRIPLET-1", "sex": "Female"}],
			}
		)
		self.addCleanup(_delete_and_commit, "Livestock Event", result["name"])
		self._register_birth_family_cleanup(result["name"], [c["animal"] for c in result["calves"]])
		self.assertEqual(len(result["calves"]), 1)
		# Subset, not equality — see the note on record_calf_births' own contract
		# test: a dropped key is the silent failure, an added one is harmless.
		self.assertLessEqual({"animal", "tag", "sex"}, set(result["calves"][0].keys()))
		self.assertEqual(result["calves"][0]["sex"], "Female")

	def test_record_birth_rejects_abortion_as_an_outcome(self):
		"""Before Task 10, Abortion ran through this same "no calf loop" gate as a
		custom_calving_outcome value (see test_record_birth_still_birth_creates_no_birth_events
		for the sibling case that still applies). Task 10 removed Abortion from that
		Select entirely — pregnancy loss is now its own Livestock Event Type, recorded
		directly (see TestLivestockEventAbortion) rather than through record_birth's
		outcome parameter. record_birth must now fail cleanly for that outcome —
		via the Select's own "cannot be Abortion" validation surfacing as an error,
		not a crash — and create no Calving row at all, rather than silently
		succeeding with zero calves as it used to.
		"""
		from upande_livestock.serverscripts.breeding.record_birth import record_birth

		self._confirm_pregnancy(service_date="2025-09-11", diagnosis_date="2025-10-15")
		before = frappe.db.count("Livestock Event", {"event_type": "Calving"})
		result = record_birth(
			{
				"dam": self.dam,
				"operator": self.operator,
				"event_date": "2026-07-08",
				"outcome": "Abortion",
				"calves": [{"name": "N-A"}],
			}
		)
		self.assertNotIn("ok", result)
		self.assertIn("error", result)
		self.assertIn("Abortion", result["error"])
		self.assertEqual(frappe.db.count("Livestock Event", {"event_type": "Calving"}), before)

	def test_record_birth_still_birth_creates_no_birth_events(self):
		"""Same gate as Abortion, exercised with a real (non-sentinel) calf tag —
		Still Birth must create zero Birth events too, matching pre-Task-9
		behaviour exactly.
		"""
		from upande_livestock.serverscripts.breeding.record_birth import record_birth

		self._confirm_pregnancy(service_date="2025-09-12", diagnosis_date="2025-10-16")
		result = record_birth(
			{
				"dam": self.dam,
				"operator": self.operator,
				"event_date": "2026-07-09",
				"outcome": "Still Birth",
				"calves": [{"name": "TEST-TRIPLET-1", "sex": "Female"}],
			}
		)
		self.addCleanup(_delete_and_commit, "Livestock Event", result["name"])
		self.assertTrue(result["ok"])
		self.assertEqual(len(result["calves"]), 0)
		self.assertEqual(
			frappe.db.count("Livestock Event", {"related_calving": result["name"], "event_type": "Birth"}),
			0,
		)
		self.assertFalse(frappe.db.exists("Animal", "TEST-TRIPLET-1"))

	def test_record_birth_stillborn_sentinel_creates_no_animal(self):
		from upande_livestock.serverscripts.breeding.record_birth import record_birth

		self._confirm_pregnancy(service_date="2025-09-02", diagnosis_date="2025-10-06")
		before = frappe.db.count("Animal")
		result = record_birth(
			{
				"dam": self.dam,
				"operator": self.operator,
				"event_date": "2026-07-03",
				"outcome": "Still Birth",
				"calves": [{"name": "STILLBORN"}],
			}
		)
		self.addCleanup(_delete_and_commit, "Livestock Event", result["name"])
		self._register_birth_family_cleanup(result["name"], [c["animal"] for c in result["calves"]])
		self.assertTrue(result["ok"])
		self.assertEqual(frappe.db.count("Animal"), before)

	def test_only_one_place_creates_a_calf_animal(self):
		"""Guard against the two-paths regression that first prompted this.

		Once asserted against api/operations.py, which held every endpoint. That
		file is gone — the endpoints are one per module under serverscripts/ — so
		the same guarantee now has to be asserted across the whole package: no
		endpoint may create an Animal directly. `common/animal.py:create_calf` is
		the one place, and the Livestock Event controller is what calls it.
		"""
		import pathlib

		root = pathlib.Path(frappe.get_app_path("upande_livestock", "serverscripts"))
		offenders = [
			str(path.relative_to(root))
			for path in root.rglob("*.py")
			if path.name != "animal.py"
			and "tests" not in path.parts
			and 'frappe.new_doc("Animal")' in path.read_text()
		]
		self.assertEqual(offenders, [], f"a second path creates a calf Animal: {offenders}")


class TestLivestockEventCalfFieldsMandatory(IntegrationTestCase):
	"""calf_tag_number / calf_sex carry mandatory_depends_on, which Frappe 16
	enforces only in the browser (see LivestockEvent.validate()'s CALF TAG /
	CALF SEX block). The negative tests below are the point: they exercise the
	exact path that used to slip through — a Birth event that already has
	`animal` set, so create_calf_if_needed() no-ops and never gets a chance to
	enforce these fields itself (that enforcement lived only inside
	create_calf(), which this path never reaches).
	"""

	def setUp(self):
		ensure_livestock_event_types()
		self.dam = make_animal("TEST-CALFFIELD-DAM").name
		self.addCleanup(_delete_and_commit, "Animal", self.dam)
		self.calf = make_animal("TEST-CALFFIELD-CALF").name
		self.addCleanup(_delete_and_commit, "Animal", self.calf)
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def _cleanup_by_remarks(self, marker):
		self.addCleanup(
			lambda: (frappe.db.delete("Livestock Event", {"remarks": marker}), frappe.db.commit())
		)

	def test_birth_with_animal_preset_and_no_tag_throws(self):
		marker = f"calf-tag-mandatory-test-{frappe.generate_hash(length=8)}"
		self._cleanup_by_remarks(marker)
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Birth",
				"event_date": "2026-06-04",
				"operator": self.operator,
				"dam": self.dam,
				"animal": self.calf,
				"calf_sex": "Female",
				"remarks": marker,
			}
		)
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_birth_with_animal_preset_and_no_sex_throws(self):
		marker = f"calf-sex-mandatory-test-{frappe.generate_hash(length=8)}"
		self._cleanup_by_remarks(marker)
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Birth",
				"event_date": "2026-06-04",
				"operator": self.operator,
				"dam": self.dam,
				"animal": self.calf,
				"calf_tag_number": "TEST-CALFFIELD-CALF",
				"remarks": marker,
			}
		)
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_birth_with_junk_calf_sex_throws(self):
		marker = f"calf-sex-junk-test-{frappe.generate_hash(length=8)}"
		self._cleanup_by_remarks(marker)
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Birth",
				"event_date": "2026-06-04",
				"operator": self.operator,
				"dam": self.dam,
				"animal": self.calf,
				"calf_tag_number": "TEST-CALFFIELD-CALF",
				"calf_sex": "Unknown",
				"remarks": marker,
			}
		)
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_stillborn_birth_submits_with_neither_field(self):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Birth",
				"event_date": "2026-06-04",
				"operator": self.operator,
				"dam": self.dam,
				"is_stillborn": 1,
			}
		)
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		self.assertFalse(doc.calf_tag_number)
		self.assertFalse(doc.calf_sex)

	def test_feeding_event_with_neither_field_still_submits(self):
		"""The calf-field rule must not leak to other event types."""
		doc = make_event("Feeding", self.dam, "2026-06-04", operator=self.operator)
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)


class TestLivestockEventAbortion(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		self.animal = make_animal("TEST-ABORT-1").name
		self.addCleanup(_delete_and_commit, "Animal", self.animal)
		self.operator = frappe.db.get_value("Employee", {}, "name")
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", None)
		frappe.clear_cache()

	def tearDown(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", None)
		frappe.clear_cache()

	def _confirm_pregnancy(self, service_date="2026-01-10", diagnosis_date="2026-01-20"):
		"""Create a submitted, Confirmed Service + Pregnancy Diagnosis for self.animal.

		Built through real inserts (no flags.ignore_validate), so this is the
		actual trail LivestockEvent.validate()'s ABORTION auto-link has to
		resolve against — a Confirmed Service with no Calving recorded against
		it — not a shortcut that would silently diverge from what production
		callers produce. Returns the submitted Service doc.
		"""
		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Service",
				"event_date": service_date,
				"operator": self.operator,
				"service_type": "A.I.",
				"service_date": service_date,
			}
		)
		service.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", service.name)
		service.submit()

		diagnosis = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Pregnancy Diagnosis",
				"event_date": diagnosis_date,
				"operator": self.operator,
				"related_service": service.name,
				"diagnosis_date": diagnosis_date,
				"diagnosis_result": "Confirmed",
			}
		)
		diagnosis.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", diagnosis.name)
		diagnosis.submit()
		return service

	def _abortion(self, event_date, **kwargs):
		"""Insert an Abortion with no custom_related_pregnancy set — exactly
		what every reachable caller (the desk form, since the client script no
		longer nulls this field for Abortion; the REST API; data import)
		actually sends. LivestockEvent.validate()'s ABORTION block is what
		must resolve the link, not this helper.
		"""
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Abortion",
				"event_date": event_date,
				"operator": self.operator,
				"abortion_cause": "Unknown",
				**kwargs,
			}
		)
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		doc.submit()
		return doc

	def test_abortion_is_a_seeded_event_type_that_creates_no_animal(self):
		self.assertTrue(frappe.db.exists("Livestock Event Type", "Abortion"))
		self.assertFalse(frappe.db.get_value("Livestock Event Type", "Abortion", "creates_animal"))

	def test_abortion_removed_from_calving_outcome_options(self):
		field = frappe.get_meta("Livestock Event").get_field("custom_calving_outcome")
		self.assertNotIn("Abortion", (field.options or "").split("\n"))

	def test_abortion_creates_no_animal(self):
		before = frappe.db.count("Animal")
		self._abortion("2026-08-01")
		self.assertEqual(frappe.db.count("Animal"), before)

	def test_abortion_without_cause_throws(self):
		"""abortion_cause carries mandatory_depends_on, which Frappe 16 enforces
		only in the browser (see LivestockEvent.validate()'s ABORTION CAUSE
		block). This is the regression test for the exact gap that pattern has
		already shipped once for operator/animal/calf_tag_number/calf_sex: a
		hand-built doc (REST API, data import, mobile client) reaching insert()
		with the field unset.
		"""
		marker = f"abortion-cause-mandatory-test-{frappe.generate_hash(length=8)}"
		self.addCleanup(
			lambda: (frappe.db.delete("Livestock Event", {"remarks": marker}), frappe.db.commit())
		)
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Abortion",
				"event_date": "2026-08-07",
				"operator": self.operator,
				"remarks": marker,
			}
		)
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_abortion_closes_the_pregnancy_on_the_dam(self):
		# A freshly created Animal already starts at repro_status "Open" with no
		# expected_calving_date (see make_animal/Animal defaults) — asserting
		# those two values straight off self.animal would pass trivially even
		# with close_pregnancy_after_abortion stubbed to a no-op, since there
		# would be nothing to "close" in the first place. Set the dam to a
		# served/pregnant state first so this test actually exercises the reset.
		frappe.db.set_value("Animal", self.animal, "repro_status", "Pregnant")
		frappe.db.set_value("Animal", self.animal, "expected_calving_date", "2026-12-01")
		self._abortion("2026-08-02")
		dam = frappe.get_doc("Animal", self.animal)
		self.assertEqual(dam.repro_status, "Open")
		# custom_pregnancy_status does not exist on Animal on this site (no DocField,
		# no Custom Field — confirmed via meta and a direct DESCRIBE of tabAnimal),
		# even though close_pregnancy_after_abortion() and several pre-existing
		# call sites (before_insert's Service/Pregnancy Diagnosis/Calving blocks)
		# all guard it the same way. Assert the guarded behaviour only when the
		# field is actually present, so this test exercises the real setter on any
		# site that does carry the field, without hard-failing on one that doesn't.
		if dam.meta.has_field("custom_pregnancy_status"):
			self.assertEqual(dam.custom_pregnancy_status, "Not Pregnant")
		self.assertFalse(dam.expected_calving_date)

	def test_abortion_auto_links_the_confirmed_pregnancy(self):
		"""The regression test for C2: the desk form (and REST API, and data
		import) never sets custom_related_pregnancy for an Abortion — the
		client script no longer nulls it, but nothing populates it either.
		LivestockEvent.validate()'s ABORTION block must resolve it on its own,
		exactly like the pre-existing Calving auto-link.
		"""
		service = self._confirm_pregnancy(service_date="2026-01-10", diagnosis_date="2026-01-20")
		abortion = self._abortion("2026-05-10")
		self.assertEqual(abortion.custom_related_pregnancy, service.name)

	def test_abortion_fails_the_related_service(self):
		service = self._confirm_pregnancy(service_date="2026-01-10", diagnosis_date="2026-01-20")
		self._abortion("2026-05-10")
		service.reload()
		self.assertEqual(service.service_status, "Failed")
		self.assertEqual(service.pregnancy_confirmation_status, "Aborted")

	def test_gestation_days_at_loss_is_computed(self):
		self._confirm_pregnancy(service_date="2026-01-10", diagnosis_date="2026-01-20")
		abortion = self._abortion("2026-05-10")
		self.assertEqual(abortion.gestation_days_at_loss, 120)

	def test_abortion_with_no_confirmed_pregnancy_proceeds_unlinked(self):
		"""The judgement call behind the auto-link: when nothing resolves (no
		Confirmed pregnancy on file for this animal at all), the Abortion must
		still be recordable rather than thrown away. Throwing here would
		protect against nothing — Service Rule 2 can only ever throw for a
		Confirmed pregnancy with no linked Calving, and this is precisely the
		case where no such row exists — while blocking a real loss for a cow
		whose confirmation paperwork was never entered.
		"""
		abortion = self._abortion("2026-08-09")
		self.assertFalse(abortion.custom_related_pregnancy)
		self.assertFalse(abortion.gestation_days_at_loss)

	def test_abortion_does_not_increment_parity(self):
		before = frappe.db.get_value("Animal", self.animal, "parity") or 0
		self._abortion("2026-08-03")
		after = frappe.db.get_value("Animal", self.animal, "parity") or 0
		self.assertEqual(after, before)

	def test_ready_for_service_date_uses_the_setting(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 40)
		frappe.clear_cache()
		abortion = self._abortion("2026-08-04")
		self.assertEqual(str(abortion.ready_for_service_date), frappe.utils.add_days("2026-08-04", 40))

	def test_service_before_the_abortion_window_is_blocked(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 30)
		frappe.clear_cache()
		self._abortion("2026-08-05")
		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Service",
				"event_date": "2026-08-15",
				"service_date": "2026-08-15",
				"operator": self.operator,
			}
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			service.insert()

	def test_zero_setting_disables_the_block(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 0)
		frappe.clear_cache()
		self._abortion("2026-08-06")
		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Service",
				"event_date": "2026-08-16",
				"service_date": "2026-08-16",
				"operator": self.operator,
			}
		)
		service.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", service.name)
		self.assertTrue(service.name)

	def test_service_after_abortion_succeeds_without_the_pregnancy_deadlock(self):
		"""C2's actual user-visible bug, reproduced end to end: before the
		auto-link existed, a desk-recorded Abortion carried no
		custom_related_pregnancy, so the Confirmed Service it should have
		closed out was never marked Failed/Aborted and never got a linked
		Calving either — meaning Service Rule 2's NOT EXISTS check kept
		matching that same Confirmed pregnancy forever, throwing "Animal is
		Already Pregnant!" on every subsequent Service for that cow, with no
		way to recover short of editing a submitted document. Proves the fix:
		once the Abortion auto-links and fails the Service, a later Service
		for the same animal must succeed.
		"""
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 0)
		frappe.clear_cache()
		self._confirm_pregnancy(service_date="2026-01-10", diagnosis_date="2026-01-20")
		self._abortion("2026-05-10")

		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Service",
				"event_date": "2026-05-15",
				"service_date": "2026-05-15",
				"operator": self.operator,
			}
		)
		service.insert()  # must not throw "Animal is Already Pregnant!"
		self.addCleanup(_delete_and_commit, "Livestock Event", service.name)
		self.assertTrue(service.name)

	def test_new_pregnancy_can_be_confirmed_after_abortion(self):
		"""Finding 2 (Important, whole-branch review): LivestockEvent.on_submit's
		"cow must calve before a new pregnancy can be recorded" rule looks for a
		Calving dated after the PREVIOUS Confirmed Pregnancy Diagnosis — and an
		Abortion never produces a Calving. So even once the animal can be
		re-served after an Abortion (test above), submitting her NEXT Confirmed
		Pregnancy Diagnosis would throw "already pregnant... must calve" forever,
		since no Calving will ever exist to satisfy the check. Proves the fix:
		an Abortion dated after the previous Confirmed diagnosis satisfies the
		rule exactly as a Calving would, and the Calving path is untouched.
		"""
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 0)
		frappe.clear_cache()
		self._confirm_pregnancy(service_date="2026-01-10", diagnosis_date="2026-01-20")
		self._abortion("2026-05-10")

		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Service",
				"event_date": "2026-05-15",
				"service_date": "2026-05-15",
				"operator": self.operator,
			}
		)
		service.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", service.name)
		service.submit()

		diagnosis = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Pregnancy Diagnosis",
				"event_date": "2026-06-01",
				"operator": self.operator,
				"related_service": service.name,
				"diagnosis_date": "2026-06-01",
				"diagnosis_result": "Confirmed",
			}
		)
		diagnosis.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", diagnosis.name)
		diagnosis.submit()  # must not throw "already pregnant... must calve"
		self.assertEqual(diagnosis.docstatus, 1)


class TestLivestockEventAbortionAwareServiceCheckJS(IntegrationTestCase):
	"""Finding 1 (Important, whole-branch review) is client-side JS
	(public/js/livestock_event.js) with no test harness in this app — there is
	no way here to drive a browser and prove the desk form's own Service
	validation actually stops throwing after an Abortion. See the fix report
	for what remains genuinely unverified.

	What CAN be pinned cheaply, and is pinned below: that the specific check
	the fix targets was actually edited to know about Abortion at all, keyed
	on the same custom_related_pregnancy linkage the server populates — rather
	than the fix silently missing its target or drifting from that linkage.
	This is a shape assertion over the source text, not behavioural proof.
	"""

	def test_service_pregnancy_check_js_knows_about_abortion(self):
		js_path = frappe.get_app_path("upande_livestock", "public", "js", "livestock_event.js")
		with open(js_path) as f:
			source = f.read()
		# The one block this fix touches: the desk form's "Check active
		# pregnancy" Service validation (originally Calving-only).
		marker = source.index("Check active pregnancy")
		check_block = source[marker : marker + 1200]
		self.assertIn("Abortion", check_block)
		self.assertIn("custom_related_pregnancy", check_block)


class TestCalvingPregnancyLinkIsAService(IntegrationTestCase):
	"""`custom_related_pregnancy` on a Calving must name a Service event.

	Every reader of this field joins it against a Service: breeding_lists'
	ready-for-service query (api/operations.py), the overdue-pregnancy-check
	scheduler (tasks.py), this controller's own "not already calved" guard, the
	Abortion auto-link, and the gestation-length check immediately below the
	link resolution — which reads `service_date` off whatever it points at.

	The auto-resolver populates it correctly, but only runs when the field is
	blank. The write endpoints (record_calf_births, create_abortion_event) set
	it straight from a client-supplied `related_pregnancy` with no check, and
	the clients have been sending Pregnancy Diagnosis names. A Diagnosis has no
	`service_date`, so the join silently matches nothing and the gestation check
	silently skips: a served cow's Service never closes and she is never listed
	as ready to serve again.

	These pin the field's type so a client cannot reintroduce that.
	"""

	def setUp(self):
		ensure_livestock_event_types()
		self.operator = frappe.db.get_value("Employee", {}, "name")
		self.animal = make_animal("TEST-PREGLINK-DAM").name
		self.addCleanup(_delete_and_commit, "Animal", self.animal)

	def _service_and_diagnosis(self, animal, service_date="2025-09-01", diagnosis_date="2025-10-05"):
		"""A submitted Confirmed Service plus the Diagnosis that confirmed it."""
		service = make_event(
			"Service", animal, service_date, service_type="A.I.", service_date=service_date
		)
		self.addCleanup(_delete_and_commit, "Livestock Event", service.name)
		service.submit()

		diagnosis = make_event(
			"Pregnancy Diagnosis",
			animal,
			diagnosis_date,
			related_service=service.name,
			diagnosis_date=diagnosis_date,
			diagnosis_result="Confirmed",
		)
		self.addCleanup(_delete_and_commit, "Livestock Event", diagnosis.name)
		diagnosis.submit()
		return service, diagnosis

	def _calving(self, animal, related_pregnancy, event_date="2026-06-08"):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": animal,
				"event_type": "Calving",
				"event_date": event_date,
				"operator": self.operator,
				"custom_calving_outcome": "Live Birth",
				"custom_no_of_calves": 1,
				"custom_related_pregnancy": related_pregnancy,
			}
		)
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		return doc

	def test_a_calving_may_not_point_its_pregnancy_at_a_diagnosis(self):
		"""The exact shape found on kaitet.local: 10 of 14 Calvings did this."""
		_, diagnosis = self._service_and_diagnosis(self.animal)
		with self.assertRaises(frappe.ValidationError) as caught:
			self._calving(self.animal, diagnosis.name)
		self.assertIn("must be a Service event", str(caught.exception))

	def test_a_calving_may_not_point_at_another_animals_service(self):
		"""A Service for a different cow is not this cow's pregnancy."""
		other = make_animal("TEST-PREGLINK-OTHER").name
		self.addCleanup(_delete_and_commit, "Animal", other)
		other_service, _ = self._service_and_diagnosis(other)
		self._service_and_diagnosis(self.animal)
		with self.assertRaises(frappe.ValidationError) as caught:
			self._calving(self.animal, other_service.name)
		self.assertIn("belongs to", str(caught.exception))

	def test_a_calving_pointing_at_its_own_service_is_accepted(self):
		"""The correct linkage must keep working — this guards over-rejection."""
		service, _ = self._service_and_diagnosis(self.animal)
		calving = self._calving(self.animal, service.name)
		self.assertEqual(calving.custom_related_pregnancy, service.name)

	def test_an_abortion_may_not_point_its_pregnancy_at_a_diagnosis(self):
		"""create_abortion_event sets the same field from the same client input.

		The Abortion auto-link resolves a Service (see the ABORTION block in
		validate), and `warn_on_calving_mismatch` and the desk form's own check
		both read this field expecting one, so an Abortion carrying a Diagnosis
		is as broken as a Calving carrying one.
		"""
		_, diagnosis = self._service_and_diagnosis(self.animal)
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Abortion",
				"event_date": "2026-01-15",
				"operator": self.operator,
				# Mandatory for an Abortion. Supplied so the insert fails on the
				# pregnancy link and not on MandatoryError, which is also a
				# ValidationError and would make this test pass for free.
				"abortion_cause": "Unknown",
				"custom_related_pregnancy": diagnosis.name,
			}
		)
		with self.assertRaises(frappe.ValidationError) as caught:
			doc.insert()
		self.assertIn("must be a Service event", str(caught.exception))
