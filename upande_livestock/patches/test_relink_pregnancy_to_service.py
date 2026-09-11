# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The repair for Calvings whose pregnancy link names a Diagnosis.

Written against the shape actually found on the Kaitet site: of 14 submitted
Calvings, none pointed at a Service, ten pointed at a Pregnancy Diagnosis and
four were blank. Every one of the ten resolved through the Diagnosis's own
`related_service` to a real Service with a plausible gestation (267-288 days),
so the repair is a lookup, not a guess.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import ensure_livestock_event_types
from upande_livestock.patches.relink_pregnancy_to_service import execute


def _purge(doctype, name):
	herd = frappe.db.get_value("Animal", name, "current_herd") if doctype == "Animal" else None
	frappe.db.delete(doctype, {"name": name})
	# A raw delete skips Animal.after_delete, which is what recomputes the
	# headcount. A calving now moves the dam into the milking herd, so a fixture
	# torn down this way left that herd counting a cow who no longer exists.
	if herd:
		from upande_livestock.serverscripts.common.animal import recompute_herd_count

		recompute_herd_count(herd)
	frappe.db.commit()


class TestRelinkPregnancyToService(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		self.operator = frappe.db.get_value("Employee", {}, "name")
		self.animal = self._animal("TEST-RELINK-DAM")

	def _animal(self, tag):
		if not frappe.db.exists("Animal", tag):
			frappe.get_doc(
				{
					"doctype": "Animal",
					"tag_number": tag,
					"burn_name": tag,
					"sex": "Female",
					"status": "Active",
				}
			).insert()
		self.addCleanup(_purge, "Animal", tag)
		return tag

	def _event(self, event_type, animal, event_date, **kw):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": animal,
				"event_type": event_type,
				"event_date": event_date,
				"operator": self.operator,
				**kw,
			}
		)
		doc.insert()
		self.addCleanup(_purge, "Livestock Event", doc.name)
		doc.submit()
		# A submitted calving moves the dam into the milking herd, as a Movement
		# of its own. This fixture owns that row too, or it outlives the animal
		# it points at and leaves the herd count one too many.
		if event_type == "Calving":
			for spawned in frappe.get_all(
				"Livestock Event",
				filters={"animal": animal, "event_type": "Movement"},
				pluck="name",
			):
				self.addCleanup(_purge, "Livestock Event", spawned)
		return doc

	def _service_and_diagnosis(self, animal, service_date="2025-09-01"):
		service = self._event(
			"Service", animal, service_date, service_type="A.I.", service_date=service_date
		)
		diagnosis = self._event(
			"Pregnancy Diagnosis",
			animal,
			"2025-10-05",
			related_service=service.name,
			diagnosis_date="2025-10-05",
			diagnosis_result="Confirmed",
		)
		return service, diagnosis

	def _mislinked_calving(self, animal, points_at, event_date="2026-06-08"):
		"""A Calving carrying the bad link.

		Written with the validation bypassed, because the validation added
		alongside this patch is precisely what stops it being written that way
		now — the rows this patch repairs all pre-date it.
		"""
		calving = self._event(
			"Calving",
			animal,
			event_date,
			custom_calving_outcome="Live Birth",
			custom_no_of_calves=1,
		)
		frappe.db.set_value(
			"Livestock Event", calving.name, "custom_related_pregnancy", points_at,
			update_modified=False,
		)
		frappe.db.commit()
		return calving

	def _link(self, name):
		return frappe.db.get_value("Livestock Event", name, "custom_related_pregnancy")

	def test_a_calving_pointing_at_a_diagnosis_is_repointed_to_its_service(self):
		service, diagnosis = self._service_and_diagnosis(self.animal)
		calving = self._mislinked_calving(self.animal, diagnosis.name)
		self.assertEqual(self._link(calving.name), diagnosis.name)

		execute()

		self.assertEqual(self._link(calving.name), service.name)

	def test_a_calving_already_pointing_at_a_service_is_left_alone(self):
		service, _ = self._service_and_diagnosis(self.animal)
		calving = self._mislinked_calving(self.animal, service.name)

		execute()

		self.assertEqual(self._link(calving.name), service.name)

	def test_a_diagnosis_with_no_service_is_skipped_not_blanked(self):
		"""An unresolvable row keeps its bad link and is reported, not cleared.

		Blanking would destroy the only evidence of what the row meant, and the
		repair has no way to reconstruct it.
		"""
		# related_service is mandatory on a Diagnosis, so an unresolvable one can
		# only arise the way a legacy row would: written valid, then orphaned.
		_, orphan = self._service_and_diagnosis(self.animal)
		frappe.db.set_value(
			"Livestock Event", orphan.name, "related_service", None, update_modified=False
		)
		frappe.db.commit()
		calving = self._mislinked_calving(self.animal, orphan.name)

		execute()

		self.assertEqual(self._link(calving.name), orphan.name)

	def test_running_twice_changes_nothing(self):
		service, diagnosis = self._service_and_diagnosis(self.animal)
		calving = self._mislinked_calving(self.animal, diagnosis.name)

		execute()
		first = self._link(calving.name)
		execute()

		self.assertEqual(self._link(calving.name), first)
		self.assertEqual(first, service.name)
