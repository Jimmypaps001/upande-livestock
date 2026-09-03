# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Tests for the Livestock Operations block's write endpoints.

Every endpoint here is wrapped by ``_run``, which converts an exception into
``{"error": ...}`` rather than raising. Tests therefore assert on the returned
dict — ``_assert_ok`` surfaces the server's message on failure, otherwise a
broken endpoint reads as a bland "None != True".

Cleanup is explicit. IntegrationTestCase rolls back once at class teardown, not
per test, and ``frappe.delete_doc(force=True)`` neither cascades nor bypasses the
submitted-record guard — so ``_purge`` cancels before deleting, and every created
document is registered with addCleanup.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, today

from upande_livestock.api.operations import (
	_active_animals,
	create_abortion_event,
	create_check_up,
	create_health_case,
	create_pregnancy_diagnosis,
	create_service_event,
	create_weight_record,
	disposal_options,
	health_options,
	record_disposal,
	weight_options,
)

COMPANY = "Kaitet Group"


def _employee():
	return frappe.db.get_value("Employee", {}, "name")


def _purge(doctype, name):
	"""Cancel then delete. Submitted documents cannot be deleted outright."""
	if not frappe.db.exists(doctype, name):
		return
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus == 1:
		try:
			doc.cancel()
		except Exception:
			frappe.db.set_value(doctype, name, "docstatus", 2, update_modified=False)
	frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	frappe.db.commit()


def _purge_events_for(animal):
	"""Drop every Livestock Event pointing at `animal`, newest first.

	Timeline events created by sync_event_for() are owned by their detail document
	but are separate records, so they need removing in their own right.
	"""
	for row in frappe.get_all(
		"Livestock Event", filters={"animal": animal}, fields=["name"], order_by="creation desc"
	):
		_purge("Livestock Event", row.name)


def _make_cow(tag, months_old=48, herd=None, sex="Female"):
	"""An animal old enough to clear the service and calving age guards."""
	if frappe.db.exists("Animal", tag):
		return frappe.get_doc("Animal", tag)
	return frappe.get_doc(
		{
			"doctype": "Animal",
			"tag_number": tag,
			"burn_name": tag,
			"sex": sex,
			"status": "Active",
			"date_of_birth": add_months(today(), -months_old),
			"current_herd": herd,
		}
	).insert(ignore_permissions=True)


def _suspend_sex_routing(case):
	"""Point the sex-specific calf herds at nothing for the duration of a test.

	Tests that exercise the calf-herd FALLBACK chain — an explicit setting, the
	calf-rearing flag, the age bracket — need sex routing out of the way, because
	it answers first in resolve_calf_herd() and the fallback under test never runs.

	Both writes commit. Several of these tests commit mid-run, so a suspension
	left uncommitted would become durable while the restore was undone by the
	class teardown rollback, leaving the site with no calf herds at all.
	"""
	saved = {}
	for field in ("female_calf_herd", "male_calf_herd"):
		saved[field] = frappe.db.get_single_value("Livestock Settings", field)
		frappe.db.set_single_value("Livestock Settings", field, None)
	frappe.db.commit()
	frappe.clear_cache(doctype="Livestock Settings")

	def restore():
		for f, v in saved.items():
			frappe.db.set_single_value("Livestock Settings", f, v)
		frappe.db.commit()
		frappe.clear_cache(doctype="Livestock Settings")

	case.addCleanup(restore)


def _assert_ok(case, res, what):
	case.assertTrue(res.get("ok"), f"{what} failed: {res.get('error')}")
	return res


class TestEventDateFallback(IntegrationTestCase):
	"""event_date is canonical — a form that sends only the type-specific date
	must not leave event_date defaulting to today."""

	def setUp(self):
		self.cow = _make_cow("ZZ OPS DATE COW")
		self.addCleanup(_purge, "Animal", self.cow.name)
		self.addCleanup(_purge_events_for, self.cow.name)

	def test_service_date_becomes_event_date(self):
		backdated = add_days(today(), -30)
		res = _assert_ok(
			self,
			create_service_event(
				{
					"animal": self.cow.name,
					"service_type": "A.I.",
					"service_date": backdated,
					"operator": _employee(),
				}
			),
			"create_service_event",
		)
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertEqual(str(event.service_date), backdated)
		self.assertEqual(
			str(event.event_date),
			backdated,
			"event_date should follow service_date, not default to today",
		)

	def test_explicit_event_date_wins(self):
		service_date = add_days(today(), -30)
		explicit = add_days(today(), -20)
		res = _assert_ok(
			self,
			create_service_event(
				{
					"animal": self.cow.name,
					"service_type": "A.I.",
					"service_date": service_date,
					"event_date": explicit,
					"operator": _employee(),
				}
			),
			"create_service_event",
		)
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertEqual(str(event.event_date), explicit)

	def test_diagnosis_date_becomes_event_date(self):
		service_date = add_days(today(), -40)
		_assert_ok(
			self,
			create_service_event(
				{
					"animal": self.cow.name,
					"service_type": "A.I.",
					"service_date": service_date,
					"operator": _employee(),
				}
			),
			"create_service_event",
		)
		diag_date = add_days(today(), -10)
		res = _assert_ok(
			self,
			create_pregnancy_diagnosis(
				{
					"animal": self.cow.name,
					"diagnosis_result": "Confirmed",
					"diagnosis_date": diag_date,
					"operator": _employee(),
				}
			),
			"create_pregnancy_diagnosis",
		)
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertEqual(str(event.diagnosis_date), diag_date)
		self.assertEqual(str(event.event_date), diag_date)


class TestActiveAnimalsFilter(IntegrationTestCase):
	def test_disabled_animals_are_excluded(self):
		cow = _make_cow("ZZ OPS ACTIVE COW")
		self.addCleanup(_purge, "Animal", cow.name)
		self.assertIn(cow.name, [a.name for a in _active_animals()])

		# `disabled` alone must be enough — status stays Active here on purpose, so
		# the status predicate cannot be what does the excluding.
		frappe.db.set_value("Animal", cow.name, "disabled", 1, update_modified=False)
		self.assertNotIn(cow.name, [a.name for a in _active_animals()])


class TestAbortion(IntegrationTestCase):
	def setUp(self):
		self.cow = _make_cow("ZZ OPS ABORT COW")
		self.addCleanup(_purge, "Animal", self.cow.name)
		self.addCleanup(_purge_events_for, self.cow.name)

	def test_cause_is_required(self):
		res = create_abortion_event({"animal": self.cow.name, "operator": _employee()})
		self.assertFalse(res.get("ok"))
		self.assertIn("cause", (res.get("error") or "").lower())

	def test_records_an_abortion_event(self):
		res = _assert_ok(
			self,
			create_abortion_event(
				{
					"animal": self.cow.name,
					"abortion_cause": "Infectious",
					"event_date": today(),
					"abortion_notes": "test",
					"operator": _employee(),
				}
			),
			"create_abortion_event",
		)
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertEqual(event.event_type, "Abortion")
		self.assertEqual(event.abortion_cause, "Infectious")
		self.assertEqual(event.docstatus, 1)

	def test_abortion_causes_are_offered(self):
		res = _assert_ok(self, health_options(), "health_options")
		self.assertIn("Infectious", res["abortion_causes"])


class TestWeightRecord(IntegrationTestCase):
	def setUp(self):
		self.cow = _make_cow("ZZ OPS WEIGHT COW")
		self.addCleanup(_purge, "Animal", self.cow.name)

	def test_records_a_weight(self):
		res = _assert_ok(
			self,
			create_weight_record(
				{
					"animal": self.cow.name,
					"company": COMPANY,
					"weight_date": today(),
					"weight_kg": 412.5,
					"method": "Platform Scale",
					"measured_by": _employee(),
				}
			),
			"create_weight_record",
		)
		self.addCleanup(_purge, "Livestock Weight Record", res["name"])
		doc = frappe.get_doc("Livestock Weight Record", res["name"])
		self.assertEqual(doc.weight_kg, 412.5)
		self.assertEqual(doc.docstatus, 1)

	def test_zero_weight_is_rejected(self):
		res = create_weight_record({"animal": self.cow.name, "company": COMPANY, "weight_kg": 0})
		self.assertFalse(res.get("ok"))

	def test_options_offer_the_methods(self):
		res = _assert_ok(self, weight_options(), "weight_options")
		self.assertIn("Platform Scale", res["methods"])


class TestHealthEndpoints(IntegrationTestCase):
	def setUp(self):
		self.cow = _make_cow("ZZ OPS HEALTH COW")
		self.addCleanup(_purge, "Animal", self.cow.name)
		self.addCleanup(_purge_events_for, self.cow.name)

	def test_check_up_creates_a_check_up_timeline_event(self):
		res = _assert_ok(
			self,
			create_check_up(
				{
					"animal": self.cow.name,
					"company": COMPANY,
					"diagnosis_date": today(),
					"operator": _employee(),
					"action_taken": "Logged — monitor",
					"temperature_c": 38.6,
				}
			),
			"create_check_up",
		)
		self.addCleanup(_purge, "Livestock Diagnosis", res["name"])
		event = frappe.db.get_value(
			"Livestock Event",
			{"reference_doctype": "Livestock Diagnosis", "reference_name": res["name"]},
			["event_type", "animal"],
			as_dict=True,
		)
		self.assertIsNotNone(event, "LivestockDiagnosis.on_submit should sync a timeline event")
		self.assertEqual(event.event_type, "Check Up")
		self.assertEqual(event.animal, self.cow.name)

	def test_check_up_requires_an_action(self):
		res = create_check_up({"animal": self.cow.name, "company": COMPANY, "operator": _employee()})
		self.assertFalse(res.get("ok"))

	def test_health_case_creates_a_health_case_timeline_event(self):
		res = _assert_ok(
			self,
			create_health_case(
				{
					"animal": self.cow.name,
					"company": COMPANY,
					"opened_date": today(),
					"case_status": "Open",
					"presenting_symptoms": "Off feed, warm to touch",
					"severity": "Moderate",
					"opened_by": _employee(),
				}
			),
			"create_health_case",
		)
		self.addCleanup(_purge, "Livestock Health Case", res["name"])
		event = frappe.db.get_value(
			"Livestock Event",
			{"reference_doctype": "Livestock Health Case", "reference_name": res["name"]},
			["event_type", "animal"],
			as_dict=True,
		)
		self.assertIsNotNone(event, "LivestockHealthCase.on_submit should sync a timeline event")
		self.assertEqual(event.event_type, "Health Case")

	def test_health_case_requires_symptoms(self):
		res = create_health_case({"animal": self.cow.name, "company": COMPANY, "opened_by": _employee()})
		self.assertFalse(res.get("ok"))


class TestDisposal(IntegrationTestCase):
	def test_disposal_retires_the_animal(self):
		"""The animal is left uncapitalised on purpose.

		LivestockDisposal.post_asset_disposal() downgrades a missing Asset to a
		warning, so this exercises the retirement half — the status change and the
		`disabled` flag — without needing asset accounting in the test site.
		"""
		cow = _make_cow("ZZ OPS DISPOSE COW")
		self.addCleanup(_purge, "Animal", cow.name)
		res = _assert_ok(
			self,
			record_disposal(
				{
					"animal": cow.name,
					"disposal_type": "Died — Disease",
					"disposal_date": today(),
					"reason_details": "test",
				}
			),
			"record_disposal",
		)
		self.addCleanup(_purge, "Livestock Disposal", res["name"])
		self.assertEqual(res["animal_status"], "Dead")
		self.assertEqual(res["animal_disabled"], 1)
		# And it must drop straight out of the data-entry lists.
		self.assertNotIn(cow.name, [a.name for a in _active_animals()])

	def test_disposal_type_is_required(self):
		cow = _make_cow("ZZ OPS DISPOSE COW 2")
		self.addCleanup(_purge, "Animal", cow.name)
		res = record_disposal({"animal": cow.name, "disposal_date": today()})
		self.assertFalse(res.get("ok"))

	def test_options_offer_the_disposal_types(self):
		res = _assert_ok(self, disposal_options(), "disposal_options")
		self.assertIn("Sold", res["disposal_types"])


class TestOneSourceForBreedingWorklists(IntegrationTestCase):
	"""`breeding_lists` is the only endpoint answering these two questions.

	`api/reproduction.py` carried a second, independent implementation of both
	worklists. Nothing imported it, but it was whitelisted, so a client could
	reach it — and it disagreed: on kaitet.local it reported 8 animals ready to
	serve against breeding_lists' 2, because it sidestepped the
	`custom_related_pregnancy` corruption instead of being subject to it.

	It was also wrong in ways breeding_lists is not: no Animal status filter, so
	a dead or sold cow could be listed; a hardcoded 60-day wait instead of the
	Calving's configured `ready_for_service_date`; and one row per calving
	rather than per animal.

	Two endpoints answering "which cows can I serve today" is the failure this
	app already decided against once (see "one call for eligibility, so a client
	cannot decide it differently"). These pin the removal.
	"""

	def test_reproduction_no_longer_answers_ready_for_service(self):
		from upande_livestock.api import reproduction

		self.assertFalse(
			hasattr(reproduction, "get_animals_ready_for_service"),
			"the duplicate ready-for-service worklist is back",
		)

	def test_reproduction_no_longer_answers_pregnancy_checks(self):
		from upande_livestock.api import reproduction

		self.assertFalse(
			hasattr(reproduction, "get_animals_needing_pregnancy_check"),
			"the duplicate pregnancy-check worklist is back",
		)

	def test_breeding_lists_still_answers_both(self):
		from upande_livestock.api.operations import breeding_lists

		result = breeding_lists()
		self.assertTrue(result.get("ok"), result.get("error"))
		self.assertIn("ready_for_service", result)
		self.assertIn("pregnancy_checks", result)
