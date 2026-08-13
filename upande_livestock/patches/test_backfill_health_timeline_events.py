# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.backfill_health_timeline_events import execute

ANIMAL_TAG = "TEST-BACKFILL-1"


def _delete_and_commit(doctype, filters):
	"""Hard-delete (raw SQL) and commit — see test_livestock_event_link.py's
	helper of the same name for why a raw delete is used instead of
	frappe.delete_doc here."""
	frappe.db.delete(doctype, filters)
	frappe.db.commit()


class TestBackfillHealthTimelineEvents(IntegrationTestCase):
	def test_creates_exactly_one_event_per_submitted_detail_document(self):
		"""Runs the real patch against real, already-live kaitet.local data:
		3 submitted Livestock Diagnosis and 25 submitted Livestock Health Case
		rows. A stubbed `execute(): pass` would leave these counts at 0/0."""
		execute()
		dx_count = frappe.db.count("Livestock Diagnosis", {"docstatus": 1})
		hc_count = frappe.db.count("Livestock Health Case", {"docstatus": 1})
		checkup_events = frappe.db.count("Livestock Event", {"event_type": "Check Up"})
		case_events = frappe.db.count("Livestock Event", {"event_type": "Health Case"})
		self.assertEqual(checkup_events, dx_count)
		self.assertEqual(case_events, hc_count)

	def test_patch_is_idempotent(self):
		execute()
		before = frappe.db.count("Livestock Event")
		names_before = set(frappe.db.sql_list("SELECT name FROM `tabLivestock Event`"))
		execute()
		self.assertEqual(frappe.db.count("Livestock Event"), before)
		self.assertEqual(set(frappe.db.sql_list("SELECT name FROM `tabLivestock Event`")), names_before)

	def test_no_detail_document_has_two_events(self):
		execute()
		dupes = frappe.db.sql(
			"""
			SELECT reference_doctype, reference_name, COUNT(*) c
			FROM `tabLivestock Event`
			WHERE reference_name IS NOT NULL AND reference_name != ''
			GROUP BY reference_doctype, reference_name
			HAVING c > 1
			""",
			as_dict=True,
		)
		self.assertEqual(dupes, [])

	def test_backfilled_event_animal_matches_source_document(self):
		execute()
		dx_mismatches = frappe.db.sql(
			"""
			SELECT e.name FROM `tabLivestock Event` e
			JOIN `tabLivestock Diagnosis` dx ON dx.name = e.reference_name
			WHERE e.reference_doctype = 'Livestock Diagnosis' AND e.animal != dx.animal
			"""
		)
		self.assertEqual(dx_mismatches, ())
		hc_mismatches = frappe.db.sql(
			"""
			SELECT e.name FROM `tabLivestock Event` e
			JOIN `tabLivestock Health Case` hc ON hc.name = e.reference_name
			WHERE e.reference_doctype = 'Livestock Health Case' AND e.animal != hc.animal
			"""
		)
		self.assertEqual(hc_mismatches, ())

	def test_backfilled_events_are_named_by_type_and_submitted(self):
		execute()
		bad_check_up = frappe.db.sql(
			"SELECT name FROM `tabLivestock Event` WHERE event_type = 'Check Up' "
			"AND (name NOT REGEXP '^CHECK-UP-[0-9]{4}-[0-9]{5}$' OR docstatus != 1)"
		)
		self.assertEqual(bad_check_up, ())
		bad_health_case = frappe.db.sql(
			"SELECT name FROM `tabLivestock Event` WHERE event_type = 'Health Case' "
			"AND (name NOT REGEXP '^HEALTH-CASE-[0-9]{4}-[0-9]{5}$' OR docstatus != 1)"
		)
		self.assertEqual(bad_health_case, ())

	def test_execute_creates_an_event_for_a_real_submitted_diagnosis(self):
		"""Drive execute() against a throwaway submitted Diagnosis that has no
		event yet, not just assert about data that may already be backfilled.

		By the time this test runs against a live site, execute() may already
		have run for real, which would let the assertions above pass even
		against a stubbed `execute(): pass` if every existing row already
		carried its event from an earlier run. This test creates its own
		submitted Diagnosis, proves it starts with zero events, then proves
		execute() gives it exactly one.
		"""
		frappe.db.delete("Livestock Event", {"animal": ANIMAL_TAG})
		frappe.db.delete("Livestock Diagnosis", {"animal": ANIMAL_TAG})
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
		self.addCleanup(_delete_and_commit, "Animal", {"name": animal.name})

		operator = frappe.db.get_value("Employee", {}, "name")
		dx = frappe.get_doc(
			{
				"doctype": "Livestock Diagnosis",
				"animal": animal.name,
				"diagnosis_date": "2026-04-07",
				"operator": operator,
			}
		).insert()
		self.addCleanup(_delete_and_commit, "Livestock Diagnosis", {"name": dx.name})

		# Force docstatus to submitted with a raw SQL update rather than
		# dx.submit(), which would invoke LivestockDiagnosis.on_submit() and
		# create the event immediately — defeating the point of this fixture,
		# which is to reproduce "submitted before the timeline existed": a
		# document with no event yet.
		frappe.db.set_value("Livestock Diagnosis", dx.name, "docstatus", 1)
		frappe.db.commit()
		self.addCleanup(
			_delete_and_commit,
			"Livestock Event",
			{"reference_doctype": "Livestock Diagnosis", "reference_name": dx.name},
		)

		self.assertEqual(
			frappe.db.count(
				"Livestock Event", {"reference_doctype": "Livestock Diagnosis", "reference_name": dx.name}
			),
			0,
		)

		execute()

		events = frappe.get_all(
			"Livestock Event",
			filters={"reference_doctype": "Livestock Diagnosis", "reference_name": dx.name},
			fields=["name", "event_type", "animal", "docstatus"],
		)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].event_type, "Check Up")
		self.assertEqual(events[0].animal, animal.name)
		self.assertEqual(events[0].docstatus, 1)

		# And a second run must not add a second one.
		execute()
		self.assertEqual(
			frappe.db.count(
				"Livestock Event", {"reference_doctype": "Livestock Diagnosis", "reference_name": dx.name}
			),
			1,
		)
