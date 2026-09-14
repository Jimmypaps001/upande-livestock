# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Jobs done to many animals at once: a weighing morning and a drug round.

NEITHER OF THESE IS ONE ANIMAL AT A TIME. Nobody vaccinates one cow and comes
back tomorrow for the next, and nobody puts the scale up for a single calf — a
vaccination morning is a herd through a crush and a weighing is a race full of
them. The screens took one animal each, which made the two commonest jobs on
the farm the ones the app was no use for.

The behaviour these protect above the others: ONE REFUSAL MUST NOT COST THE
ROUND. Eighty-four cows weighed and lost because of the two that would not is
the worst possible answer, so the batch reports per animal and carries on.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from upande_livestock.serverscripts.husbandry.create_husbandry_event import create_husbandry_event
from upande_livestock.serverscripts.tests.test_operations import (
	_make_cow,
	_purge,
	_purge_events_for,
)
from upande_livestock.serverscripts.weights.record_weights import record_weights


def _employee():
	return frappe.db.get_value("Employee", {"status": "Active"}, "name")


def _tidy(animal):
	for row in frappe.get_all("Livestock Weight Record", filters={"animal": animal}, pluck="name"):
		_purge("Livestock Weight Record", row)
	_purge_events_for(animal)
	if frappe.db.exists("Animal", animal):
		frappe.delete_doc("Animal", animal, force=True, ignore_permissions=True)
	frappe.db.commit()


class TestAWeighingIsAMorningNotAMoment(IntegrationTestCase):
	def setUp(self):
		self.cows = ["WEIGH-BATCH-1", "WEIGH-BATCH-2", "WEIGH-BATCH-3"]
		for tag in self.cows:
			_tidy(tag)
			_make_cow(tag, herd="Lactating group 1")
			self.addCleanup(_tidy, tag)
		self.who = _employee()

	def _run(self, rows, **kw):
		return record_weights({
			"measured_by": self.who,
			"method": "Platform Scale",
			"event_date": today(),
			"weights": rows,
			**kw,
		})

	def test_a_race_full_of_cows_is_one_round(self):
		got = self._run([{"animal": t, "weight_kg": 400 + i} for i, t in enumerate(self.cows)])
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["count"], 3)

	def test_every_weight_lands_on_its_own_animal(self):
		"""A batch is a convenience for the person typing, not for the record.

		Each cow gets her own weight record — the batch must not average them,
		attribute them to a herd, or lose which number belonged to whom.
		"""
		self._run([{"animal": t, "weight_kg": 400 + i} for i, t in enumerate(self.cows)])
		for i, tag in enumerate(self.cows):
			self.assertEqual(
				frappe.db.get_value("Livestock Weight Record", {"animal": tag}, "weight_kg"),
				400 + i,
			)

	def test_a_cow_that_did_not_get_on_the_scale_is_skipped_not_failed(self):
		"""Blank is a cow who was not weighed. It is not an error to report.

		The two mean different things to whoever reads the result, and calling
		a blank row a failure would make a clean morning look like a broken one.
		"""
		got = self._run([
			{"animal": self.cows[0], "weight_kg": 410},
			{"animal": self.cows[1]},
		])
		self.assertEqual(got["count"], 1)
		self.assertEqual([s["animal"] for s in got["skipped"]], [self.cows[1]])
		self.assertFalse(got["failed"])

	def test_a_girth_with_no_weight_is_skipped_and_says_why(self):
		"""The doctype needs a weight and does not work one out from a tape.

		The old screen's hint said it did. A girth on its own is a measurement
		with nowhere to live, so it is reported rather than written into a
		record that would drop it.
		"""
		got = self._run([{"animal": self.cows[0], "heart_girth_cm": 170}])
		self.assertEqual(got["count"], 0)
		self.assertIn("girth", got["skipped"][0]["why"])

	def test_the_cows_already_weighed_survive_a_later_refusal(self):
		"""The one behaviour the whole batch exists for.

		A failing row used to roll the transaction back to the start of the
		request, taking every cow already written with it — and the answer
		still listed them as recorded. Each row is its own savepoint now.
		"""
		got = self._run([
			{"animal": self.cows[0], "weight_kg": 410},
			{"animal": "WEIGH-BATCH-NOBODY", "weight_kg": 420},
		])
		self.assertEqual(got["count"], 1)
		self.assertTrue(
			frappe.db.exists("Livestock Weight Record", got["recorded"][0]["name"]),
			"the cow weighed before the refusal was rolled back with it",
		)

	def test_one_refusal_does_not_cost_the_round(self):
		got = self._run([
			{"animal": self.cows[0], "weight_kg": 410},
			{"animal": "WEIGH-BATCH-NOBODY", "weight_kg": 420},
			{"animal": self.cows[2], "weight_kg": 430},
		])
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["count"], 2)
		self.assertEqual([f["animal"] for f in got["failed"]], ["WEIGH-BATCH-NOBODY"])

	def test_a_refusal_says_which_animal_and_why(self):
		"""'Something went wrong' is not an answer when 86 cows went through."""
		got = self._run([{"animal": self.cows[0], "weight_kg": 410}], method="Telepathy")
		self.assertTrue(got["failed"])
		self.assertTrue(got["failed"][0]["why"].strip())

	def test_an_empty_round_is_refused_rather_than_silently_doing_nothing(self):
		self.assertIn("at least one", self._run([]).get("error", ""))


class TestADrugRoundIsAHerdThroughACrush(IntegrationTestCase):
	def setUp(self):
		self.herd = "Lactating group 1"
		self.cows = ["ROUND-DOSE-1", "ROUND-DOSE-2"]
		for tag in self.cows:
			_tidy(tag)
			_make_cow(tag, herd=self.herd)
			self.addCleanup(_tidy, tag)
		self.who = _employee()

	def test_a_set_of_animals_is_one_call(self):
		got = create_husbandry_event({
			"event_type": "Hoof Trimming",
			"animals": self.cows,
			"event_date": today(),
			"operator": self.who,
		})
		self.assertTrue(got.get("ok"), got.get("error"))

	def test_one_event_is_written_per_animal(self):
		"""A withdrawal date is a fact about a cow, not about a pen.

		The round is batched for the person at the crush; the record is not,
		because 'this pen was dosed' cannot tell you in six days which cow's
		milk may go in the tank.
		"""
		create_husbandry_event({
			"event_type": "Hoof Trimming",
			"animals": self.cows,
			"event_date": today(),
			"operator": self.who,
		})
		for tag in self.cows:
			self.assertTrue(
				frappe.db.exists("Livestock Event", {
					"animal": tag, "event_type": "Hoof Trimming", "docstatus": 1,
				}),
				f"{tag} has no event of her own",
			)
