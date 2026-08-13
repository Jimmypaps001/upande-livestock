# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import ensure_livestock_event_types
from upande_livestock.patches.backfill_event_date_from_twin_field import execute


def _delete_and_commit(doctype, name):
	frappe.db.delete(doctype, {"name": name})
	frappe.db.commit()


class TestBackfillEventDateFromTwinField(IntegrationTestCase):
	"""Drive the patch against throwaway fixtures, not just the real
	kaitet.local rows it was written for: once the patch has run for real,
	"every Service/Pregnancy Diagnosis event has an event_date" stays true
	forever, so asserting only that would be hollow against a stubbed
	`execute(): pass`. Each test here builds its own event starting from a
	blank event_date, so a stub fails.

	A Livestock Event with event_date blank can no longer be built with a
	plain insert() for two independent reasons: LivestockEvent.validate()'s
	own new mandatory check (the thing this patch exists to make safe) would
	reject a blank event_date on a new document, and event_date's own DocField
	default ("Today") would silently fill it back in before validate() even
	runs (Document.insert() calls _set_defaults() first). flags.ignore_validate
	dodges the first; a raw frappe.db.set_value() after insert dodges the
	second — which also mirrors how the real rows actually got here: the
	default only re-applies while a document is still new, so the live NULLs
	trace back to a *later* save (after the very first insert), not the
	original insert itself.
	"""

	def setUp(self):
		ensure_livestock_event_types()

	def _event(self, event_type, service_date=None, diagnosis_date=None, event_date=None):
		doc = frappe.get_doc({"doctype": "Livestock Event", "event_type": event_type})
		doc.flags.ignore_validate = True
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		# Force the starting state directly in the DB, bypassing both the
		# event_date "Today" default and the ORM entirely.
		frappe.db.set_value(
			"Livestock Event",
			doc.name,
			{"event_date": event_date, "service_date": service_date, "diagnosis_date": diagnosis_date},
			update_modified=False,
		)
		doc.reload()
		return doc

	def test_fills_event_date_from_service_date_when_blank(self):
		event = self._event("Service", service_date="2026-02-01")
		self.assertFalse(event.event_date)

		execute()

		event.reload()
		self.assertEqual(str(event.event_date), "2026-02-01")

	def test_fills_event_date_from_diagnosis_date_when_blank(self):
		event = self._event("Pregnancy Diagnosis", diagnosis_date="2026-02-15")
		self.assertFalse(event.event_date)

		execute()

		event.reload()
		self.assertEqual(str(event.event_date), "2026-02-15")

	def test_does_not_overwrite_an_existing_event_date(self):
		"""event_date already set (even to a different date than the twin
		field) is left exactly as-is — this patch fills blanks, it does not
		reconcile disagreements."""
		event = self._event("Service", service_date="2026-02-01", event_date="2026-02-10")

		execute()

		event.reload()
		self.assertEqual(str(event.event_date), "2026-02-10")

	def test_skips_when_the_twin_field_is_also_blank(self):
		"""Nothing to copy — must not throw and must leave event_date blank."""
		event = self._event("Service")
		self.assertFalse(event.service_date)

		execute()  # must not raise

		event.reload()
		self.assertFalse(event.event_date)

	def test_event_types_with_no_twin_field_are_left_alone(self):
		"""Calving has no dedicated date field to recover from — this patch
		must not guess one (e.g. from creation)."""
		event = self._event("Calving")

		execute()

		event.reload()
		self.assertFalse(event.event_date)

	def test_patch_is_idempotent(self):
		event = self._event("Service", service_date="2026-02-01")

		execute()
		event.reload()
		once = str(event.event_date)

		execute()
		event.reload()
		self.assertEqual(str(event.event_date), once)
