# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, today

from upande_livestock.install import ensure_livestock_event_types
from upande_livestock.serverscripts.common.guards import AGE_RULES, INTERVAL_RULES, animal_age_months, check_guards
from upande_livestock.serverscripts.tests.timings_utils import ResetsLivestockTimings

# The seven age/interval fields this module's tests set to None as a precondition
# ("this site never configured any of these"). Not a second copy of
# TIMING_DEFAULTS' key list — ResetsLivestockTimings (mixed in below) is what
# guarantees these end every test back at their real defaults, from the single
# definition in livestock_timings.TIMING_DEFAULTS; this tuple only drives the
# per-test "start unconfigured" setup.
SETTINGS_KEYS = (
	"min_service_age_months",
	"min_calving_age_months",
	"min_calving_interval_days",
	"min_vaccination_interval_days",
	"min_deworming_interval_days",
	"min_weight_recording_interval_days",
	"min_hoof_trimming_interval_days",
)


def _delete_and_commit(doctype, name):
	"""Hard-delete and commit.

	IntegrationTestCase gives this class a single rollback at the end of the
	whole class, not one per test, and ensure_livestock_event_types() (called
	from setUp) itself commits — so nothing inserted after that commit is ever
	rolled back automatically. Every Animal and Livestock Event these tests
	create must therefore be cleaned up (and that cleanup committed)
	explicitly, matching the pattern already established in
	test_livestock_event.py, or it is left behind in the live database
	forever, inflating tabAnimal / tabLivestock Event past their documented
	invariant counts.
	"""
	frappe.db.delete(doctype, {"name": name})
	frappe.db.commit()


class TestLivestockGuards(ResetsLivestockTimings, IntegrationTestCase):
	def setUp(self):
		# Registers the class's final "wipe every timing field, then reseed the
		# real defaults" cleanup before anything below runs, so per addCleanup's
		# LIFO order it fires last — after every Animal/Event cleanup this
		# class's tests go on to register.
		super().setUp()
		ensure_livestock_event_types()
		for key in SETTINGS_KEYS:
			frappe.db.set_single_value("Livestock Settings", key, None)
		frappe.clear_cache()
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def _animal(self, tag, age_months):
		# Defensive, not just idempotent: a stray row from an earlier
		# interrupted run must be purged (Events first, since Animal cannot be
		# deleted while a Livestock Event still links to it) before creating a
		# fresh fixture under the same tag.
		frappe.db.delete("Livestock Event", {"animal": tag})
		frappe.db.delete("Animal", {"name": tag})
		frappe.db.commit()
		animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": tag,
				"burn_name": tag,
				"sex": "Female",
				"status": "Active",
				"date_of_birth": add_months(today(), -age_months),
			}
		).insert()
		# Registered immediately after insert() returns, before the caller
		# makes any assertions, so a failing assertion still leaves the row
		# scheduled for deletion.
		self.addCleanup(_delete_and_commit, "Animal", animal.name)
		return animal

	def _event(self, event_type, animal, event_date, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": animal,
				"event_type": event_type,
				"event_date": event_date,
				"operator": self.operator,
				**kwargs,
			}
		)
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		return doc

	def _background_calving(self, animal, event_date, pregnancy):
		"""Insert-and-submit a Calving row purely as prior-event data for the
		interval guard to query against — not what any test asserts about.

		flags.ignore_validate skips LivestockEvent's own Calving-specific
		validation (pregnancy auto-link-or-throw, required calving outcome,
		gestation-length warnings) for both insert() and submit(), the same
		technique TestTimingsAreEnforcedServerSide._calving() in
		test_livestock_timings.py already uses. That is what makes it possible
		for a fixture here to hold any custom_related_pregnancy value —
		including None, to reproduce the real SHAWN-129539 shape — without
		fighting unrelated business rules that have nothing to do with the
		interval guard under test.
		"""
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": animal,
				"event_type": "Calving",
				"event_date": event_date,
				"operator": self.operator,
				"custom_related_pregnancy": pregnancy,
			}
		)
		doc.flags.ignore_validate = True
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		doc.submit()
		return doc

	def _unsaved_calving(self, animal, event_date, pregnancy):
		"""An in-memory Calving doc, never inserted.

		check_guards(doc) only reads doc.event_type/animal/event_date/name and
		doc.get(field) — it needs no other part of the document lifecycle, so
		calling it directly here targets exactly the interval-guard behaviour
		under test without also exercising (or having to satisfy)
		LivestockEvent's unrelated Calving validate() logic.
		"""
		return frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": animal,
				"event_type": "Calving",
				"event_date": event_date,
				"operator": self.operator,
				"custom_related_pregnancy": pregnancy,
			}
		)

	def test_rule_tables_cover_the_documented_defaults(self):
		self.assertEqual(AGE_RULES["Service"]["default"], 15)
		self.assertEqual(AGE_RULES["Calving"]["default"], 24)
		self.assertEqual(INTERVAL_RULES["Calving"]["default"], 270)
		self.assertEqual(INTERVAL_RULES["Deworming"]["default"], 90)
		self.assertEqual(INTERVAL_RULES["Hoof Trimming"]["default"], 90)
		self.assertEqual(INTERVAL_RULES["Weight Recording"]["default"], 7)

	def test_vaccination_has_no_interval_rule(self):
		"""custom_vaccine_drug_name does not exist on the doctype (see the
		module docstring): comparing "same vaccine too soon" is not possible,
		and a plain interval check rejects real same-visit, multi-vaccine
		recording (383 such pairs on kaitet.local). Vaccination must stay out
		of INTERVAL_RULES until that field exists."""
		self.assertNotIn("Vaccination", INTERVAL_RULES)

	def test_animal_age_months_is_computed_from_date_of_birth(self):
		animal = self._animal("TEST-GUARD-AGE", 30)
		self.assertAlmostEqual(animal_age_months(animal.name, today()), 30, delta=1)

	def test_animal_with_no_dob_is_not_age_blocked(self):
		tag = "TEST-GUARD-NODOB"
		frappe.db.delete("Livestock Event", {"animal": tag})
		frappe.db.delete("Animal", {"name": tag})
		frappe.db.commit()
		animal = frappe.get_doc(
			{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
		).insert()
		self.addCleanup(_delete_and_commit, "Animal", animal.name)
		self.assertIsNone(animal_age_months(animal.name, today()))
		doc = self._event("Service", animal.name, today(), service_date=today())
		self.assertTrue(doc.name)

	def test_service_below_minimum_age_is_blocked(self):
		animal = self._animal("TEST-GUARD-YOUNG", 10)
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._event("Service", animal.name, today(), service_date=today())

	def test_service_at_or_above_minimum_age_passes(self):
		animal = self._animal("TEST-GUARD-OLD", 20)
		doc = self._event("Service", animal.name, today(), service_date=today())
		self.assertTrue(doc.name)

	def test_configured_minimum_age_is_honoured(self):
		animal = self._animal("TEST-GUARD-OLD", 20)
		frappe.db.set_single_value("Livestock Settings", "min_service_age_months", 24)
		frappe.clear_cache()
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._event("Service", animal.name, today(), service_date=today())

	def test_missing_event_date_is_not_age_blocked(self):
		"""frappe.utils.getdate(None) silently returns *today*, not "no date".

		Without a guard, an event with no event_date would be age-checked
		against today — real data: CALVING-2026-00001 and SERVICE-2026-00001
		both have a NULL event_date and, before this fix, were age-checked
		against whatever "today" happened to be at query time. This animal is
		10 months old *today*, well under the 15-month minimum, so a bug that
		substituted today for the missing event_date would throw here.
		"""
		animal = self._animal("TEST-GUARD-NODATE", 10)
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": animal.name,
				"event_type": "Service",
				"event_date": None,
				"operator": self.operator,
			}
		)
		check_guards(doc)  # must not raise

	def test_deworming_inside_the_interval_is_blocked(self):
		animal = self._animal("TEST-GUARD-DEWORM", 30)
		first = self._event("Deworming", animal.name, add_days(today(), -5))
		first.submit()
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._event("Deworming", animal.name, today())

	def test_deworming_outside_the_interval_passes(self):
		animal = self._animal("TEST-GUARD-DEWORM2", 30)
		first = self._event("Deworming", animal.name, add_days(today(), -100))
		first.submit()
		doc = self._event("Deworming", animal.name, today())
		self.assertTrue(doc.name)

	def test_draft_events_do_not_trigger_the_interval_rule(self):
		animal = self._animal("TEST-GUARD-DRAFT", 30)
		self._event("Deworming", animal.name, add_days(today(), -5))  # left in draft
		doc = self._event("Deworming", animal.name, today())
		self.assertTrue(doc.name)

	def test_zero_setting_disables_an_interval_rule(self):
		animal = self._animal("TEST-GUARD-ZERO", 30)
		frappe.db.set_single_value("Livestock Settings", "min_deworming_interval_days", 0)
		frappe.clear_cache()
		first = self._event("Deworming", animal.name, add_days(today(), -1))
		first.submit()
		doc = self._event("Deworming", animal.name, today())
		self.assertTrue(doc.name)

	def test_untyped_event_is_not_guarded(self):
		animal = self._animal("TEST-GUARD-FEED", 3)
		doc = self._event("Feeding", animal.name, today())
		self.assertTrue(doc.name)

	def test_same_pregnancy_calvings_are_not_compared(self):
		"""Reproduces ELVIS-129348: four submitted same-day Calving rows that
		all share one custom_related_pregnancy — a multiple birth recorded as
		several rows, not several calvings too close together."""
		animal = self._animal("TEST-GUARD-TWINS", 30)
		anchor = self._event("Feeding", animal.name, add_days(today(), -100))
		self._background_calving(animal.name, today(), pregnancy=anchor.name)
		current = self._unsaved_calving(animal.name, today(), pregnancy=anchor.name)
		check_guards(current)  # must not raise

	def test_calvings_with_no_pregnancy_link_are_still_compared(self):
		"""Reproduces SHAWN-129539: two Calving rows with a NULL
		custom_related_pregnancy. NULL must not silently escape the exemption
		— two calvings that share nothing are still too close together."""
		animal = self._animal("TEST-GUARD-NULLPREG", 30)
		self._background_calving(animal.name, today(), pregnancy=None)
		current = self._unsaved_calving(animal.name, today(), pregnancy=None)
		with self.assertRaises(frappe.exceptions.ValidationError):
			check_guards(current)

	def test_different_pregnancy_calvings_are_still_compared(self):
		"""Two real, distinct pregnancies for the same animal must still be
		held to the interval — the exemption is for one calving split across
		records, not a blanket pass for every Calving row that happens to
		have some pregnancy link."""
		animal = self._animal("TEST-GUARD-DIFFPREG", 30)
		anchor_a = self._event("Feeding", animal.name, add_days(today(), -200))
		anchor_b = self._event("Feeding", animal.name, add_days(today(), -100))
		self._background_calving(animal.name, today(), pregnancy=anchor_a.name)
		current = self._unsaved_calving(animal.name, today(), pregnancy=anchor_b.name)
		with self.assertRaises(frappe.exceptions.ValidationError):
			check_guards(current)

	def test_empty_string_pregnancy_link_does_not_falsely_exempt(self):
		"""'' IS NOT NULL is true in SQL, so a bare IS NOT NULL check would
		treat two unrelated Calving rows that both happen to hold '' (a Link
		field cleared through some UI or import path, rather than left NULL)
		as sharing a pregnancy and wrongly exempt them — the same failure
		class as the NULL case above, just via a different sentinel. Verified
		separately that frappe stores '' as given here rather than
		normalising it to NULL on insert, so the ORM path is enough; no raw
		SQL workaround needed to reproduce this shape.
		"""
		animal = self._animal("TEST-GUARD-EMPTYPREG", 30)
		self._background_calving(animal.name, today(), pregnancy="")
		current = self._unsaved_calving(animal.name, today(), pregnancy="")
		with self.assertRaises(frappe.exceptions.ValidationError):
			check_guards(current)
