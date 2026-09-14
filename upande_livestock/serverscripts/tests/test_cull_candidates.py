# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which cows the figures put forward, and why each one is there.

The suggestion list is the one part of culling that nobody signs — it only
decides what a manager reads first. That makes two things worth protecting:
that a cow with a clean record is never on it, and that a cow who IS on it
carries the facts that put her there. A ranked list with no reasons is an
oracle, and the whole point of this endpoint is that the argument can be read
rather than trusted.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.culling.cull_candidates import cull_candidates
from upande_livestock.serverscripts.tests.test_operations import (
	_make_cow,
	_purge,
	_purge_events_for,
)


def _tidy(animal):
	for row in frappe.get_all("Livestock Health Case", filters={"animal": animal}, pluck="name"):
		_purge("Livestock Health Case", row)
	_purge_events_for(animal)
	if frappe.db.exists("Animal", animal):
		frappe.delete_doc("Animal", animal, force=True, ignore_permissions=True)
	frappe.db.commit()


def _employee():
	"""Every hand-entered event says who recorded it, fixtures included."""
	return frappe.db.get_value("Employee", {"status": "Active"}, "name")


def _event(animal, kind, on, **kw):
	doc = frappe.get_doc({
		"doctype": "Livestock Event",
		"animal": animal,
		"event_type": kind,
		"event_date": on,
		"operator": _employee(),
		**kw,
	}).insert(ignore_permissions=True)
	doc.submit()
	return doc


def _find(got, animal):
	for row in got["candidates"]:
		if row["animal"] == animal:
			return row
	return None


def _reasons(row):
	return {r["key"] for r in (row or {}).get("reasons", [])}


class TestOnlyCowsWithSomethingOnTheirRecordAreSuggested(IntegrationTestCase):
	def setUp(self):
		self.clean = "CAND-CLEAN-1"
		_tidy(self.clean)
		_make_cow(self.clean, herd="Lactating group 1")
		self.addCleanup(_tidy, self.clean)

	def test_a_cow_with_nothing_against_her_is_not_on_the_list(self):
		"""No calvings, no losses, no illness — nothing to argue about.

		The list exists because four cows worth looking at were buried under
		four hundred that are fine. A cow who is merely present must not be one
		of the four.
		"""
		got = cull_candidates()
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertIsNone(_find(got, self.clean))

	def test_the_whole_herd_is_still_counted(self):
		"""`considered` is every cow looked at, not every cow suggested."""
		got = cull_candidates()
		self.assertGreaterEqual(got["considered"], got["flagged_count"])


class TestLostPregnanciesPutHerForward(IntegrationTestCase):
	def setUp(self):
		self.animal = "CAND-LOSS-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		for back in (400, 120):
			_event(self.animal, "Abortion", add_days(today(), -back), abortion_cause="Unknown")
		self.addCleanup(_tidy, self.animal)

	def test_two_losses_are_a_reason(self):
		row = _find(cull_candidates(), self.animal)
		self.assertIsNotNone(row, "a cow with two lost pregnancies is not on the list")
		self.assertIn("abortions", _reasons(row))

	def test_the_reason_says_how_many_and_when(self):
		row = _find(cull_candidates(), self.animal)
		reason = next(r for r in row["reasons"] if r["key"] == "abortions")
		self.assertIn("2", reason["label"])
		self.assertTrue(reason["detail"], "no date given for the last loss")

	def test_her_last_five_years_carry_the_losses(self):
		row = _find(cull_candidates(), self.animal)
		self.assertEqual(sum(y["abortions"] for y in row["years"]), 2)


class TestServicesThatDoNotHoldPutHerForward(IntegrationTestCase):
	def setUp(self):
		self.animal = "CAND-OPEN-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		# A calving needs a pregnancy to have ended, which needs a confirmed
		# service before it — the same chain the farm actually records.
		_event(
			self.animal, "Service", add_days(today(), -580),
			service_date=add_days(today(), -580),
			pregnancy_confirmation_status="Confirmed",
		)
		_event(self.animal, "Calving", add_days(today(), -300))
		# Each answered "Not Pregnant" before the next: the doctype refuses a
		# second service while one is still pending a diagnosis, which is the
		# same order the farm works in. Four services, four negatives.
		for back in (200, 160, 120, 80):
			_event(
				self.animal, "Service", add_days(today(), -back),
				service_date=add_days(today(), -back),
				pregnancy_confirmation_status="Not Pregnant",
				service_status="Failed",
			)
		self.addCleanup(_tidy, self.animal)

	def test_four_services_since_calving_without_holding_is_a_reason(self):
		row = _find(cull_candidates(), self.animal)
		self.assertIsNotNone(row)
		self.assertIn("not_holding", _reasons(row))

	def test_three_hundred_days_open_is_its_own_reason(self):
		"""Days open and repeat services are different facts about her.

		She may be served once and stay open for a year, or five times in three
		months. Collapsing them would lose which of the two is happening, and
		they call for different things being done about it.
		"""
		row = _find(cull_candidates(), self.animal)
		self.assertIn("open", _reasons(row))

	def test_a_confirmed_service_stops_the_count(self):
		"""She held. Nothing since then is a service that failed."""
		_event(
			self.animal, "Service", add_days(today(), -30),
			service_date=add_days(today(), -30),
			pregnancy_confirmation_status="Confirmed",
		)
		row = _find(cull_candidates(), self.animal)
		self.assertNotIn("not_holding", _reasons(row))
		self.assertNotIn("open", _reasons(row))


class TestDaysUnderTreatmentPutHerForward(IntegrationTestCase):
	def setUp(self):
		self.animal = "CAND-SICK-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.addCleanup(_tidy, self.animal)

	def _case(self, opened_back, **kw):
		frappe.get_doc({
			"doctype": "Livestock Health Case",
			"animal": self.animal,
			"opened_date": add_days(today(), -opened_back),
			"case_status": "Open",
			"presenting_symptoms": "Off her feed",
			**kw,
		}).insert(ignore_permissions=True)

	def test_a_long_illness_is_a_reason(self):
		self._case(60)
		row = _find(cull_candidates(), self.animal)
		self.assertIsNotNone(row, "sixty days under treatment did not put her forward")
		self.assertIn("sick", _reasons(row))

	def test_an_open_case_counts_its_days_to_today(self):
		"""Nobody closes a case that is not over.

		Taking `duration_days` at face value reported a cow six weeks into
		treatment as having been ill for no days at all, because the field is
		only filled in when the case is closed.
		"""
		self._case(60)
		row = _find(cull_candidates(), self.animal)
		reason = next(r for r in row["reasons"] if r["key"] == "sick")
		self.assertIn("60", reason["label"])

	def test_a_short_illness_is_not_a_reason_on_its_own(self):
		self._case(3)
		self.assertIsNone(_find(cull_candidates(), self.animal))

	def test_her_years_carry_the_days_ill(self):
		self._case(60)
		row = _find(cull_candidates(), self.animal)
		self.assertGreater(sum(y["sick_days"] for y in row["years"]), 0)


class TestTheRankingCanBeReadRatherThanTrusted(IntegrationTestCase):
	def setUp(self):
		self.worse = "CAND-RANK-WORSE"
		self.milder = "CAND-RANK-MILDER"
		for tag in (self.worse, self.milder):
			_tidy(tag)
			_make_cow(tag, herd="Lactating group 1")
			self.addCleanup(_tidy, tag)
		for back in (500, 300, 100):
			_event(self.worse, "Abortion", add_days(today(), -back), abortion_cause="Unknown")
		_event(self.milder, "Abortion", add_days(today(), -100), abortion_cause="Unknown")
		_event(self.milder, "Abortion", add_days(today(), -400), abortion_cause="Unknown")

	def test_the_score_is_the_sum_of_the_reasons(self):
		"""So a number nobody can take apart never drives the order."""
		row = _find(cull_candidates(), self.worse)
		self.assertEqual(row["score"], sum(r["weight"] for r in row["reasons"]))

	def test_three_losses_outrank_two(self):
		got = cull_candidates()
		worse = _find(got, self.worse)
		milder = _find(got, self.milder)
		self.assertIsNotNone(worse)
		self.assertIsNotNone(milder)
		self.assertGreater(worse["score"], milder["score"])

	def test_the_farm_is_told_milk_is_not_per_animal(self):
		"""Milk Recording is a herd and a session on this farm.

		So no ranking here can honestly be about litres, and the screen has to
		be able to say so rather than implying a comparison it never made.
		"""
		self.assertFalse(cull_candidates()["per_animal_milk"])
