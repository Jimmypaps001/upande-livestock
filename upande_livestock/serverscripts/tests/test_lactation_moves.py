# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""When a milking cow is due out of the herd she is in.

THE LACTATING HERDS ARE NOT ON A CLOCK THE WAY THE CALF PENS ARE. A weaner
leaves her pen because she has been in it long enough. A high yielder leaves
because she is four months in calf and her yield is falling away — the farm's
rule is written from CONCEPTION, so a cow served late stays where she is and one
that caught early steps down early. Counting her days in the pen instead would
move the wrong cows, and it would move them all at once.

Nothing on this site has a confirmed pregnancy — fifty services, none answered —
so every case here is built rather than found. That is the point: the rule
cannot be checked against the farm's data because the farm has not recorded the
thing it depends on, which is itself worth knowing.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import herd_movement as hm
from upande_livestock.serverscripts.tests.test_culling import _employee, _tidy
from upande_livestock.serverscripts.tests.test_operations import _make_cow

COW = "LACT-MOVE-1"


def _settings():
	s = hm.settings()
	return s.get("high_yield_herd"), s.get("low_yield_herd"), s.get("steamer_herd")


def _confirmed_service(animal, served_on):
	"""A service that has been answered, which is what the rule counts from."""
	doc = frappe.new_doc("Livestock Event")
	doc.event_type = "Service"
	doc.animal = animal
	doc.event_date = served_on
	doc.service_date = served_on
	doc.operator = _employee()
	doc.pregnancy_confirmation_status = "Confirmed"
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	doc.db_set("docstatus", 1, update_modified=False)
	frappe.db.commit()
	return doc.name


class TestAHighYielderStepsDownWhenSheIsInCalf(IntegrationTestCase):
	def setUp(self):
		self.high, self.low, self.steamers = _settings()
		if not (self.high and self.low):
			self.skipTest("this site has no high/low yield herds configured")
		self.limit = int(hm.settings().get("high_yield_days_from_conception") or 0)
		if not self.limit:
			self.skipTest("no high_yield_days_from_conception set")
		_tidy(COW)
		_make_cow(COW, herd=self.high)
		frappe.db.commit()
		self.addCleanup(_tidy, COW)

	def test_a_cow_who_is_not_carrying_is_not_due_anywhere(self):
		"""She may be overdue on another rule — a cow who has failed to conceive
		at all — but she is not late for a move she has no reason to make."""
		self.assertIsNone(hm.lactation_move_due(COW))

	def test_she_is_due_once_she_is_far_enough_in_calf(self):
		_confirmed_service(COW, add_days(today(), -self.limit - 1))
		row = hm.lactation_move_due(COW)
		self.assertIsNotNone(row)
		self.assertTrue(row["due"])
		self.assertEqual(row["next_herd"], self.low)

	def test_she_is_not_due_the_day_before(self):
		"""The rule is a date, not a mood."""
		_confirmed_service(COW, add_days(today(), -self.limit + 2))
		row = hm.lactation_move_due(COW)
		self.assertFalse(row["due"])

	def test_the_count_runs_from_the_service_not_from_the_scan(self):
		"""A cow scanned at 45 days conceived 45 days before anybody looked at
		her; counting from the scan keeps her in the high-yield herd six weeks
		past the farm's own rule."""
		served = add_days(today(), -self.limit - 5)
		_confirmed_service(COW, served)
		self.assertEqual(str(hm.conception_date(COW)), served)
		self.assertGreaterEqual(hm.lactation_move_due(COW)["days_in_herd"], self.limit)

	def test_a_week_past_the_rule_is_late_not_merely_due(self):
		_confirmed_service(COW, add_days(today(), -self.limit - hm.LACTATION_GRACE_DAYS - 3))
		row = hm.lactation_move_due(COW)
		self.assertTrue(row["overdue"])
		self.assertGreater(row["days_over"], hm.LACTATION_GRACE_DAYS)

	def test_a_day_past_it_is_due_but_not_late(self):
		"""Otherwise every cow due today reads as a cow somebody forgot."""
		_confirmed_service(COW, add_days(today(), -self.limit - 1))
		row = hm.lactation_move_due(COW)
		self.assertTrue(row["due"])
		self.assertFalse(row["overdue"])

	def test_she_says_why_in_the_farms_own_terms(self):
		_confirmed_service(COW, add_days(today(), -self.limit - 1))
		self.assertIn("in calf", hm.lactation_move_due(COW)["reason"])

	def test_the_suggestion_list_carries_her(self):
		_confirmed_service(COW, add_days(today(), -self.limit - 1))
		rows = {r["animal"]: r for r in hm.lactation_suggestions()}
		self.assertIn(COW, rows)
		self.assertEqual(rows[COW]["to_herd"], self.low)
		self.assertTrue(rows[COW]["label"])

	def test_the_movement_screen_gets_one_list_not_two(self):
		"""A herdsman moving animals does not care whether the rule counted days
		in a pen or days in calf, only that she is due out."""
		_confirmed_service(COW, add_days(today(), -self.limit - 1))
		everything = {r["animal"] for r in hm.suggestions()["growth"]}
		self.assertIn(COW, everything)


class TestTheOtherTwoRungs(IntegrationTestCase):
	def setUp(self):
		self.high, self.low, self.steamers = _settings()
		if not (self.low and self.steamers):
			self.skipTest("this site has no low-yield or steamer herd configured")
		_tidy(COW)
		frappe.db.commit()
		self.addCleanup(_tidy, COW)

	def test_a_low_yielder_is_due_on_her_days_in_that_herd(self):
		"""The farm states this one as its own number — two months — rather than
		as a second offset from conception, so it is read as one."""
		limit = int(hm.settings().get("low_yield_days") or 0)
		if not limit:
			self.skipTest("no low_yield_days set")
		_make_cow(COW, herd=self.low)
		_confirmed_service(COW, add_days(today(), -limit - 30))
		row = hm.lactation_move_due(COW)
		self.assertIsNotNone(row)
		self.assertEqual(row["next_herd"], self.steamers)
		self.assertIn("low-yield herd", row["reason"])

	def test_an_in_calf_heifer_is_due_when_calving_is_close(self):
		"""She arrived already carrying, so waiting long enough is not the
		question — how near she is to calving is."""
		incalf = hm.settings().get("incalf_heifer_herd")
		lead = int(hm.settings().get("steamer_days_from_heifers") or 0)
		gestation = int(hm.settings().get("gestation_period_days") or 0) or 270
		if not (incalf and lead):
			self.skipTest("no in-calf herd or lead time configured")
		_make_cow(COW, herd=incalf)
		# Served so that calving is just inside the lead time.
		_confirmed_service(COW, add_days(today(), -(gestation - lead + 2)))
		row = hm.lactation_move_due(COW)
		self.assertIsNotNone(row)
		self.assertTrue(row["due"])
		self.assertEqual(row["next_herd"], self.steamers)
		self.assertLessEqual(row["days_to_calving"], lead)
