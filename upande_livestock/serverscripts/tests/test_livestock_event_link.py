# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import ensure_livestock_event_types

ANIMAL_TAG = "TEST-LINK-1"


def _delete_and_commit(doctype, filters):
	"""Hard-delete (raw SQL, bypassing docstatus/link checks) and commit.

	IntegrationTestCase gives this class a single rollback at the end of the
	whole class, not one per test, and ensure_livestock_event_types() (called
	from setUp) itself commits — so nothing inserted after that commit is ever
	rolled back automatically. Every Animal, Livestock Diagnosis, Livestock
	Health Case and Livestock Event these tests create must therefore be
	cleaned up (and that cleanup committed) explicitly, matching the pattern
	established in test_livestock_guards.py, or it is left behind in the live
	database forever, inflating the documented invariant counts.

	A raw `frappe.db.delete` rather than `frappe.delete_doc` deliberately:
	`delete_doc` refuses to remove a submitted document (docstatus 1) without
	first cancelling it, and separately, `force=True` bypasses LinkExistsError
	without cascading, leaving a dangling Dynamic Link behind. Neither concern
	applies to a raw SQL delete of test fixtures we are discarding entirely.
	"""
	frappe.db.delete(doctype, filters)
	frappe.db.commit()


class TestLivestockEventLink(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		# Defensive: purge any stray row from an earlier interrupted run before
		# creating a fresh fixture under the same tag. Events and detail
		# documents first (a Health Case/Diagnosis referencing this animal
		# would otherwise outlive it, and an Event referencing either would
		# outlive both).
		frappe.db.delete("Livestock Event", {"animal": ANIMAL_TAG})
		frappe.db.delete("Livestock Diagnosis", {"animal": ANIMAL_TAG})
		frappe.db.delete("Livestock Health Case", {"animal": ANIMAL_TAG})
		frappe.db.delete("Animal", {"name": ANIMAL_TAG})
		frappe.db.commit()

		animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": ANIMAL_TAG,
				"burn_name": ANIMAL_TAG,
				"sex": "Female",
				"status": "Active",
			}
		).insert()
		# Registered first (in setUp, before any test registers its own
		# cleanup) so it fires last, per addCleanup's LIFO order — after every
		# Diagnosis/Health Case/Event cleanup a test method goes on to
		# register below.
		self.addCleanup(_delete_and_commit, "Animal", {"name": animal.name})
		self.animal = animal.name
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def _events_for(self, doctype, name):
		return frappe.get_all(
			"Livestock Event",
			filters={"reference_doctype": doctype, "reference_name": name},
			fields=["name", "event_type", "docstatus"],
		)

	def _new_diagnosis(self, **kwargs):
		dx = frappe.get_doc(
			{
				"doctype": "Livestock Diagnosis",
				"animal": self.animal,
				"diagnosis_date": "2026-04-01",
				"operator": self.operator,
				**kwargs,
			}
		).insert()
		# Registered right after insert(), before this document is submitted
		# (which is what actually creates its Livestock Event) — so the
		# Diagnosis cleanup is in place before anything that could raise. It
		# is registered *before* the corresponding Event cleanup below so
		# that, per LIFO, the Event is deleted first and the Diagnosis it
		# points at second — never the other way around.
		self.addCleanup(_delete_and_commit, "Livestock Diagnosis", {"name": dx.name})
		return dx

	def _new_health_case(self, **kwargs):
		hc = frappe.get_doc(
			{
				"doctype": "Livestock Health Case",
				"animal": self.animal,
				"opened_date": "2026-04-02",
				"case_status": "Open",
				# presenting_symptoms is mandatory on Livestock Health Case;
				# not part of what any test here asserts about, just fixture
				# plumbing to get past validate().
				"presenting_symptoms": "Off feed, dull",
				**kwargs,
			}
		).insert()
		self.addCleanup(_delete_and_commit, "Livestock Health Case", {"name": hc.name})
		return hc

	def _register_event_cleanup(self, doctype, name):
		# Registered after the detail document's own cleanup (see
		# _new_diagnosis/_new_health_case above), so it fires first.
		self.addCleanup(
			_delete_and_commit, "Livestock Event", {"reference_doctype": doctype, "reference_name": name}
		)

	def test_reference_fields_exist_and_are_read_only(self):
		meta = frappe.get_meta("Livestock Event")
		for fieldname in ("reference_doctype", "reference_name"):
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, f"{fieldname} missing")
			self.assertTrue(field.read_only)

	def test_submitting_a_diagnosis_creates_one_check_up_event(self):
		dx = self._new_diagnosis(diagnosis_date="2026-04-01")
		dx.submit()
		self._register_event_cleanup("Livestock Diagnosis", dx.name)
		events = self._events_for("Livestock Diagnosis", dx.name)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].event_type, "Check Up")
		self.assertTrue(events[0].name.startswith("CHECK-UP-2026-"))

	def test_submitting_a_health_case_creates_one_health_case_event(self):
		hc = self._new_health_case(opened_date="2026-04-02")
		hc.submit()
		self._register_event_cleanup("Livestock Health Case", hc.name)
		events = self._events_for("Livestock Health Case", hc.name)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].event_type, "Health Case")

	def test_sync_is_idempotent(self):
		from upande_livestock.serverscripts.common.event_link import sync_event_for

		dx = self._new_diagnosis(diagnosis_date="2026-04-03")
		dx.submit()
		self._register_event_cleanup("Livestock Diagnosis", dx.name)
		first = sync_event_for(dx, "Check Up")
		second = sync_event_for(dx, "Check Up")
		self.assertEqual(first, second)
		self.assertEqual(len(self._events_for("Livestock Diagnosis", dx.name)), 1)

	def test_cancelling_the_detail_cancels_its_event(self):
		dx = self._new_diagnosis(diagnosis_date="2026-04-04")
		dx.submit()
		self._register_event_cleanup("Livestock Diagnosis", dx.name)
		dx.cancel()
		events = self._events_for("Livestock Diagnosis", dx.name)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].docstatus, 2)

	def test_derived_event_submits_with_no_operator(self):
		"""A Health Case with no opened_by legitimately has no operator to
		carry onto its event — nobody performed a hand-entered "operation",
		the case was just observed/opened. Livestock Event.operator is
		mandatory_depends_on "eval:!doc.reference_doctype", so an event that
		does carry a reference_doctype must submit cleanly with operator
		unset. (Previously this only worked because sync_event_for set
		flags.ignore_mandatory — silently overriding the schema constraint
		rather than the schema correctly describing this case.)
		"""
		hc = self._new_health_case(opened_date="2026-04-08")
		self.assertFalse(hc.opened_by)
		hc.submit()
		self._register_event_cleanup("Livestock Health Case", hc.name)
		events = self._events_for("Livestock Health Case", hc.name)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].docstatus, 1)
		event = frappe.get_doc("Livestock Event", events[0].name)
		self.assertFalse(event.operator)
		self.assertEqual(event.reference_doctype, "Livestock Health Case")

	def test_hand_entered_event_still_requires_an_operator(self):
		"""The conditional mandatory rule must not make operator optional
		everywhere — only for events derived from a health record. A plain,
		hand-entered event (no reference_doctype) still needs one performed
		it, and insert() must still fail without it."""
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Feeding",
				"event_date": "2026-04-09",
			}
		)
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()

	def test_health_case_lists_its_check_ups(self):
		hc = self._new_health_case(opened_date="2026-04-05")
		hc.submit()
		self._register_event_cleanup("Livestock Health Case", hc.name)
		dx = self._new_diagnosis(diagnosis_date="2026-04-06", related_case=hc.name)
		dx.submit()
		self._register_event_cleanup("Livestock Diagnosis", dx.name)
		linked = frappe.get_all("Livestock Diagnosis", filters={"related_case": hc.name}, pluck="name")
		self.assertIn(dx.name, linked)
