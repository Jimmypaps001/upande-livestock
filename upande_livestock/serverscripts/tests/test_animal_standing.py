# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where an animal stands among the others: her figures, her herd's and her group's.

Three breeding cows in one test herd, with different service histories, and a
heifer, so the tests can say which way the ranking runs and who is compared with
whom. Events go in straight (db_insert, submitted): the rules for HOW a calving
is recorded are tested elsewhere; this reads what is there."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.animals.animal_standing import animal_standing
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge, _purge_events_for

HERD = "ZZ STANDING HERD"
GOOD, MIDDLE, POOR, HEIFER = "ZZ STAND A", "ZZ STAND B", "ZZ STAND C", "ZZ STAND H"
ALL = (GOOD, MIDDLE, POOR, HEIFER)


def _event(animal, kind, ago, **kw):
	ev = frappe.get_doc({"doctype": "Livestock Event", "event_type": kind, "animal": animal,
	                     "event_date": add_days(today(), -ago), **kw})
	ev.flags.ignore_validate = True
	ev.db_insert()
	frappe.db.set_value("Livestock Event", ev.name, "docstatus", 1)


def _services(animal, held, missed):
	for i in range(held):
		_event(animal, "Service", 400 - i, pregnancy_confirmation_status="Confirmed")
	for i in range(missed):
		_event(animal, "Service", 300 - i, pregnancy_confirmation_status="Not Pregnant")


class TestAnimalStanding(IntegrationTestCase):
	def setUp(self):
		self._tidy()
		if not frappe.db.exists("Herds", HERD):
			frappe.get_doc({"doctype": "Herds", "herd_name": HERD}).insert(ignore_permissions=True)
		for tag in (GOOD, MIDDLE, POOR):
			_make_cow(tag, herd=HERD)
		_make_cow(HEIFER, months_old=14, herd=HERD)
		# 1, 2 and 4 services for the one conception; calving intervals 300, 360, 420.
		for tag, missed, gap in ((GOOD, 0, 300), (MIDDLE, 1, 360), (POOR, 3, 420)):
			_services(tag, 1, missed)
			_event(tag, "Calving", 500)
			_event(tag, "Calving", 500 - gap)
		frappe.db.set_value("Animal", MIDDLE, "last_weight_kg", 500)
		frappe.db.set_value("Animal", POOR, "last_weight_kg", 400)
		self.addCleanup(self._tidy)

	def _tidy(self):
		for tag in ALL:
			_purge_events_for(tag)
			_purge("Animal", tag)
		if frappe.db.exists("Herds", HERD):
			_purge("Herds", HERD)
		frappe.db.commit()

	def metric(self, animal, key):
		got = animal_standing({"animal": animal})
		self.assertTrue(got.get("ok"), got)
		return next(m for m in got["metrics"] if m["key"] == key), got

	def test_fewer_services_is_better_and_ranks_first(self):
		m, _ = self.metric(GOOD, "services_per_conception")
		self.assertEqual(m["value"], 1.0)
		self.assertEqual(m["herd"]["top"], 33)  # best of the three breeding cows in the herd
		best = m["group"]["top"]
		m, _ = self.metric(POOR, "services_per_conception")
		self.assertEqual(m["value"], 4.0)
		self.assertEqual(m["herd"]["top"], 100)  # last of three
		self.assertGreater(m["group"]["top"], best)

	def test_calving_interval_is_the_mean_gap_and_shorter_is_better(self):
		m, _ = self.metric(GOOD, "calving_interval")
		self.assertEqual(m["value"], 300)
		m, _ = self.metric(POOR, "calving_interval")
		self.assertEqual(m["value"], 420)
		self.assertGreater(m["herd"]["top"], 33)

	def test_the_herd_includes_her_heifer_but_the_group_does_not(self):
		_, got = self.metric(GOOD, "parity")
		self.assertEqual(got["herd"]["n"], 4)
		self.assertEqual(got["group"]["key"], "breeding")
		# the farm's other breeding cows are in the group too, her heifer is not
		self.assertGreaterEqual(got["group"]["n"], 3)

	def test_a_heifer_is_compared_with_heifers_not_the_breeding_cows(self):
		m, got = self.metric(HEIFER, "calving_interval")
		self.assertEqual(got["group"]["key"], "heifer")
		self.assertIsNone(m["value"])

	def test_neutral_measures_have_an_average_and_no_rank(self):
		m, _ = self.metric(MIDDLE, "last_weight")
		self.assertEqual(m["value"], 500)
		self.assertEqual(m["herd"]["avg"], 450)  # the two weighed cows of the herd
		self.assertIsNotNone(m["group"]["avg"])
		self.assertIsNone(m["group"]["top"])

	def test_unknown_is_null_never_zero(self):
		m, _ = self.metric(HEIFER, "services_per_conception")
		self.assertIsNone(m["value"])
		self.assertIsNone(m["herd"]["top"])

	def test_it_refuses_a_stranger(self):
		self.assertIn("error", animal_standing({"animal": "ZZ NOT AN ANIMAL"}))
