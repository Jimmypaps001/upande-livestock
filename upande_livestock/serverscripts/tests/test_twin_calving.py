# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Twins, and the number each calf is given.

One calving, n calves, each numbered from its own sex's series: A for a heifer,
B for a bull, then a three-digit sequence, a slash and the year of birth.
"""

import threading

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from upande_livestock.serverscripts.common import animal_id
from upande_livestock.serverscripts.tests import test_calf_birth as _cb
from upande_livestock.serverscripts.tests.test_animal_id import _animal, _kill


def _reset_counters():
	"""Tests claim numbers and the counter outlives their rolled-back animals.
	Dropping the rows is safe: the next claim reseeds from the animals that exist."""
	frappe.db.sql("DELETE FROM `tabSeries` WHERE `name` LIKE 'ANIMALNO-%'")
	frappe.db.commit()


def tearDownModule():
	_reset_counters()


class TestTwinCalving(IntegrationTestCase):
	# Reuse the chain (cow, service, confirmed pregnancy) and the booking helper.
	setUp = _cb.TestABlankNumberIsNotADeath.setUp
	_book = _cb.TestABlankNumberIsNotADeath._book

	def test_twins_make_one_calving_and_two_sequential_calves(self):
		res = self._book([{"sex": "Female"}, {"sex": "Female"}])
		self.assertEqual(res["num_calves"], 2)
		a, b = [animal_id.parse(c["animal"]) for c in res["calves"]]
		self.assertEqual((a["prefix"], b["prefix"]), ("A", "A"))
		self.assertEqual(b["seq"], a["seq"] + 1)
		self.assertEqual(
			frappe.db.count("Livestock Event", {"animal": self.dam.name, "event_type": "Calving"}), 1)

	def test_a_mixed_pair_is_numbered_from_each_sexs_own_series(self):
		res = self._book([{"sex": "Female"}, {"sex": "Male"}])
		a, b = [animal_id.parse(c["animal"]) for c in res["calves"]]
		self.assertEqual((a["prefix"], b["prefix"]), ("A", "B"))

	def test_the_number_is_the_name_the_tag_and_the_book_number(self):
		res = self._book([{"sex": "Male"}])
		n = res["calves"][0]["animal"]
		row = frappe.db.get_value("Animal", n, ["tag_number", "book_number"], as_dict=True)
		self.assertEqual((row.tag_number, row.book_number), (n, n))

	def test_a_typed_number_from_an_old_queued_payload_is_ignored(self):
		res = self._book([{"sex": "Female", "name": "A"}])
		self.assertEqual(len(res["calves"]), 1)
		self.assertTrue(animal_id.parse(res["calves"][0]["animal"]))

	def test_a_twin_may_be_born_dead(self):
		res = self._book([{"sex": "Female"}, {"sex": "Male", "is_stillborn": 1}])
		self.assertEqual(len(res["calves"]), 1)
		self.assertEqual(res["num_calves"], 2)


class TestTheCounter(IntegrationTestCase):
	def setUp(self):
		self.made = []
		self.addCleanup(lambda: [_kill(n) for n in self.made])

	def test_claims_never_repeat_even_before_the_animal_exists(self):
		got = [animal_id.allocate("Female", today()) for _ in range(5)]
		self.assertEqual(len(set(got)), 5)
		seqs = [animal_id.parse(g)["seq"] for g in got]
		self.assertEqual(seqs, list(range(seqs[0], seqs[0] + 5)))

	def test_the_two_series_are_independent(self):
		a1 = animal_id.parse(animal_id.allocate("Female", today()))["seq"]
		b1 = animal_id.parse(animal_id.allocate("Male", today()))["seq"]
		a2 = animal_id.parse(animal_id.allocate("Female", today()))["seq"]
		self.assertEqual(a2, a1 + 1)
		self.assertNotEqual(b1, None)
		b2 = animal_id.parse(animal_id.allocate("Male", today()))["seq"]
		self.assertEqual(b2, b1 + 1)

	def test_it_steps_over_a_number_somebody_else_took(self):
		nxt = animal_id.parse(animal_id.allocate("Female", today()))
		held = animal_id.format_id("A", nxt["seq"] + 1, nxt["yy"])
		self.made.append(held)
		_animal(held, "Female")
		after = animal_id.parse(animal_id.allocate("Female", today()))
		self.assertEqual(after["seq"], nxt["seq"] + 2)

	def test_the_counter_row_is_locked_while_a_claim_is_open(self):
		"""A second connection cannot read the counter until the first commits.

		That lock is what makes two simultaneous calvings take turns. Checked at
		the SQL level: the row is read FOR UPDATE with a short wait on a second
		connection, which must time out while this transaction holds it."""
		animal_id.allocate("Female", today())
		key = animal_id._series_key("A", animal_id.year_of(today()))
		outcome = {}
		site = frappe.local.site

		def other():
			frappe.init(site=site)
			frappe.connect()
			try:
				frappe.db.sql("SET SESSION innodb_lock_wait_timeout = 1")
				frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name`=%s FOR UPDATE", key)
				outcome["blocked"] = False
			except Exception:
				outcome["blocked"] = True
			finally:
				frappe.destroy()

		t = threading.Thread(target=other)
		t.start()
		t.join(10)
		self.assertTrue(outcome.get("blocked"), "the counter row was readable mid-claim")
