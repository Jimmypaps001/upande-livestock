# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A health case is a file, and these are the rules about opening and shutting one.

THE HOSPITAL SHAPE. You are seen; if you are treated a file is opened; everything
done to you goes in it; months later you come back and a NEW file is opened,
because that is a different illness. The farm works this way and the app did
not — a case was a form anybody could fill in for any animal at any time, which
is why this site has a cow carrying three open files for what is plainly one
bout of the same thing.

The behaviour these protect above the others: A SECOND FILE IS NEVER OPENED BY
ACCIDENT. Everything else here follows from it.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common.health_case import concern, open_case_for
from upande_livestock.serverscripts.health.case_for_animal import case_for_animal
from upande_livestock.serverscripts.health.close_health_case import close_health_case
from upande_livestock.serverscripts.health.create_check_up import create_check_up
from upande_livestock.serverscripts.health.create_health_case import create_health_case
from upande_livestock.serverscripts.health.health_case_file import health_case_file
from upande_livestock.serverscripts.health.open_health_cases import open_health_cases
from upande_livestock.serverscripts.health.treat_animal import treat_animal
from upande_livestock.serverscripts.tests.timings_utils import set_setting
from upande_livestock.serverscripts.tests.test_operations import (
	_make_cow,
	_purge,
	_purge_events_for,
)


def _employee():
	return frappe.db.get_value("Employee", {"status": "Active"}, "name")


def _tidy(animal):
	for row in frappe.get_all("Livestock Health Case", filters={"animal": animal}, pluck="name"):
		_purge("Livestock Health Case", row)
	for row in frappe.get_all("Livestock Diagnosis", filters={"animal": animal}, pluck="name"):
		_purge("Livestock Diagnosis", row)
	_purge_events_for(animal)
	if frappe.db.exists("Animal", animal):
		frappe.delete_doc("Animal", animal, force=True, ignore_permissions=True)
	frappe.db.commit()


class TestACheckUpIsWhereAFileComesFrom(IntegrationTestCase):
	def setUp(self):
		self.animal = "FILE-CHECK-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.who = _employee()
		self.addCleanup(_tidy, self.animal)

	def _check(self, action, **kw):
		return create_check_up({
			"animal": self.animal, "operator": self.who,
			"reason_for_check": "Warm, off her feed", "action_taken": action, **kw,
		})

	def test_escalating_opens_the_file(self):
		"""'Escalated to Case' was a word in a dropdown and nothing happened.

		Somebody then had to remember to open a case by hand on another screen,
		which is the step that does not happen.
		"""
		got = self._check("Escalated to Case")
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertTrue(got["case_opened"])
		self.assertTrue(frappe.db.exists("Livestock Health Case", got["case"]))

	def test_escalating_twice_does_not_open_two(self):
		first = self._check("Escalated to Case")
		second = self._check("Escalated to Case")
		self.assertEqual(second["case"], first["case"])
		self.assertFalse(second["case_opened"])

	def test_a_dose_at_the_crush_asks_rather_than_opening_one(self):
		"""Only the person who looked at her knows whether it is a one-off."""
		got = self._check("Treated on Spot")
		self.assertIsNone(got["case"])
		self.assertTrue(got["suggest_case"])

	def test_the_complaint_on_the_file_is_what_the_check_said(self):
		got = self._check("Escalated to Case")
		self.assertEqual(
			frappe.db.get_value("Livestock Health Case", got["case"], "presenting_symptoms"),
			"Warm, off her feed",
		)


class TestTreatingIsTheDoorIn(IntegrationTestCase):
	def setUp(self):
		self.animal = "FILE-TREAT-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.who = _employee()
		self.addCleanup(_tidy, self.animal)

	def _treat(self, **kw):
		return treat_animal({
			"animal": self.animal, "operator": self.who,
			"treatments": [{"drug_name_text": "Oxytet", "qty": 1, "administered_by": self.who}],
			**kw,
		})

	def test_a_treatment_with_no_file_and_no_complaint_is_refused(self):
		"""Not opened silently. A file with nothing on the front of it is one
		nobody can treat from, and guessing the complaint would invent a record."""
		self.assertIn("no open file", self._treat().get("error", ""))

	def test_saying_what_is_wrong_opens_the_file_and_puts_the_dose_in_it(self):
		got = self._treat(open_new=True, presenting_symptoms="Swollen left hind quarter")
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertTrue(got["opened"])
		self.assertEqual(got["added"], 1)

	def test_the_next_dose_joins_the_file_she_has(self):
		self._treat(open_new=True, presenting_symptoms="Swollen left hind quarter")
		again = self._treat()
		self.assertFalse(again["opened"])
		self.assertEqual(again["treatments"], 2)

	def test_treating_moves_the_file_off_open_and_onto_under_treatment(self):
		"""The file should say she is being treated rather than sitting at
		'Open' until somebody remembers to change it."""
		got = self._treat(open_new=True, presenting_symptoms="Swollen quarter")
		self.assertEqual(got["case_status"], "Under Treatment")

	def test_a_treatment_with_no_drug_is_refused(self):
		got = treat_animal({"animal": self.animal, "open_new": True,
		                    "presenting_symptoms": "x", "treatments": []})
		self.assertIn("no drug on it", got.get("error", ""))

	def test_the_screen_is_told_what_she_already_has(self):
		self._treat(open_new=True, presenting_symptoms="Swollen quarter")
		standing = case_for_animal({"animal": self.animal})
		self.assertIsNotNone(standing["open_case"])
		self.assertEqual(standing["open_case"]["treatments"], 1)


class TestAFileIsClosedWithAnEnding(IntegrationTestCase):
	def setUp(self):
		self.animal = "FILE-CLOSE-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.who = _employee()
		self.addCleanup(_tidy, self.animal)
		got = treat_animal({
			"animal": self.animal, "operator": self.who, "open_new": True,
			"presenting_symptoms": "Swollen left hind quarter",
			"treatments": [{"drug_name_text": "Oxytet", "qty": 1,
			                "response_observed": "Improving", "administered_by": self.who}],
		})
		self.case = got["case"]

	def test_nothing_could_close_a_case_before_this(self):
		"""case_status and closed_date were sealed on submit, so files could be
		opened and never shut — which is where the three-open-files cow comes
		from."""
		got = close_health_case({"case": self.case, "case_status": "Recovered"})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["case_status"], "Recovered")
		self.assertEqual(
			frappe.db.get_value("Livestock Health Case", self.case, "case_status"), "Recovered"
		)

	def test_how_it_ended_is_not_optional(self):
		self.assertIn("Say how it ended", close_health_case({"case": self.case}).get("error", ""))

	def test_an_ending_the_doctype_does_not_have_is_refused(self):
		got = close_health_case({"case": self.case, "case_status": "Fine now"})
		self.assertIn("Say how it ended", got.get("error", ""))

	def test_a_file_cannot_be_closed_twice(self):
		close_health_case({"case": self.case, "case_status": "Recovered"})
		again = close_health_case({"case": self.case, "case_status": "Recovered"})
		self.assertIn("already closed", again.get("error", ""))

	def test_a_closed_file_cannot_be_written_into(self):
		close_health_case({"case": self.case, "case_status": "Recovered"})
		got = treat_animal({
			"animal": self.animal, "case": self.case,
			"treatments": [{"drug_name_text": "Oxytet", "qty": 1, "administered_by": self.who}],
		})
		self.assertIn("is closed", got.get("error", ""))

	def test_she_is_free_to_have_a_new_file_afterwards(self):
		close_health_case({"case": self.case, "case_status": "Recovered"})
		self.assertIsNone(open_case_for(self.animal))
		fresh = treat_animal({
			"animal": self.animal, "operator": self.who, "open_new": True,
			"presenting_symptoms": "Back again, same quarter",
			"treatments": [{"drug_name_text": "Oxytet", "qty": 1, "administered_by": self.who}],
		})
		self.assertTrue(fresh["opened"])
		self.assertNotEqual(fresh["case"], self.case)

	def test_the_picker_offers_open_files_only(self):
		"""It filtered on `case_status != "Closed"` and no status is called
		"Closed" — so it offered every case the farm had ever recorded,
		including the ones for cows that had died."""
		close_health_case({"case": self.case, "case_status": "Recovered"})
		offered = {c["value"] for c in open_health_cases()["cases"]}
		self.assertNotIn(self.case, offered)


class TestTheFileCanBeRead(IntegrationTestCase):
	def setUp(self):
		self.animal = "FILE-READ-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.who = _employee()
		self.addCleanup(_tidy, self.animal)
		self.case = treat_animal({
			"animal": self.animal, "operator": self.who, "open_new": True,
			"presenting_symptoms": "Swollen left hind quarter",
			"treatments": [{"drug_name_text": "Oxytet", "qty": 2,
			                "response_observed": "Worsening", "administered_by": self.who}],
		})["case"]

	def test_every_treatment_carries_its_day_of_the_case(self):
		"""A course is read as 'day one, day three, day seven'."""
		file = health_case_file({"case": self.case})
		self.assertEqual(file["entries"][0]["day"], 1)

	def test_the_drugs_are_totalled_over_the_whole_course(self):
		treat_animal({
			"animal": self.animal, "operator": self.who,
			"treatments": [{"drug_name_text": "Oxytet", "qty": 3,
			                "response_observed": "Improving", "administered_by": self.who}],
		})
		file = health_case_file({"case": self.case})
		self.assertEqual(file["drugs"][0]["qty"], 5.0)
		self.assertEqual(file["drugs"][0]["times"], 2)

	def test_it_reads_which_way_she_went(self):
		treat_animal({
			"animal": self.animal, "operator": self.who,
			"treatments": [{"drug_name_text": "Oxytet", "qty": 1,
			                "response_observed": "Resolved", "administered_by": self.who}],
		})
		self.assertEqual(health_case_file({"case": self.case})["verdict"]["reads"], "better")

	def test_it_stays_silent_where_the_record_is_silent(self):
		"""Inferring 'improving' from the fact that treatment stopped would read
		a recovery into a file that was simply abandoned."""
		quiet = treat_animal({
			"animal": self.animal, "operator": self.who, "open_new": True,
			"presenting_symptoms": "Lame off hind",
			"treatments": [{"drug_name_text": "Oxytet", "qty": 1, "administered_by": self.who}],
		})
		self.assertIn("cannot say", health_case_file({"case": quiet["case"]})["verdict"]["says"])

	def test_her_other_files_come_with_it(self):
		"""A cow on her fourth file for the same quarter in a year is a
		different conversation from one on her first."""
		close_health_case({"case": self.case, "case_status": "Recovered"})
		second = treat_animal({
			"animal": self.animal, "operator": self.who, "open_new": True,
			"presenting_symptoms": "Back again",
			"treatments": [{"drug_name_text": "Oxytet", "qty": 1, "administered_by": self.who}],
		})["case"]
		others = [o["name"] for o in health_case_file({"case": second})["others"]]
		self.assertIn(self.case, others)


class TestOpeningASecondFileIsDeliberate(IntegrationTestCase):
	def setUp(self):
		self.animal = "FILE-SECOND-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.who = _employee()
		self.addCleanup(_tidy, self.animal)
		create_health_case({
			"animal": self.animal, "opened_by": self.who,
			"presenting_symptoms": "Swollen left hind quarter",
		})

	def test_a_second_file_is_refused_unless_it_is_asked_for(self):
		got = create_health_case({
			"animal": self.animal, "opened_by": self.who,
			"presenting_symptoms": "Swollen left hind quarter",
		})
		self.assertIn("already has a file open", got.get("error", ""))

	def test_a_genuinely_different_illness_is_still_possible(self):
		"""A bad quarter and a lame foot are two files. The accident is what is
		being prevented, not the real case."""
		got = create_health_case({
			"animal": self.animal, "opened_by": self.who, "open_new": True,
			"presenting_symptoms": "Lame off hind, no swelling",
		})
		self.assertTrue(got.get("ok"), got.get("error"))


class TestTheFarmDrawsItsOwnLines(IntegrationTestCase):
	def test_a_long_open_file_is_worth_saying_something_about(self):
		case = {"case_status": "Open", "opened_date": add_days(today(), -40)}
		self.assertEqual(concern(case, add_days(today(), -1))["kind"], "long")

	def test_a_file_nobody_has_written_in_is_a_different_worry(self):
		"""She may have recovered and the file never closed, which is the reason
		a farm's open-case count stops meaning anything."""
		case = {"case_status": "Open", "opened_date": add_days(today(), -10)}
		self.assertEqual(concern(case, add_days(today(), -9))["kind"], "stale")

	def test_a_closed_file_is_never_worrying(self):
		case = {"case_status": "Recovered", "opened_date": add_days(today(), -400),
		        "closed_date": today()}
		self.assertIsNone(concern(case, None))

	def test_zero_means_do_not_tell_me(self):
		# Through set_setting, which captures what the farm had rather than
		# restoring to the documented default — a farm that configured 30 would
		# otherwise come back from this test set to 21.
		set_setting(self, "health_case_concern_days", 0)
		set_setting(self, "health_case_stale_days", 0)
		case = {"case_status": "Open", "opened_date": add_days(today(), -400)}
		self.assertIsNone(concern(case, add_days(today(), -300)))
