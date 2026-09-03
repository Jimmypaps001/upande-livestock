# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Feeding a herd in two runs, and knowing what the week's mixing is.

The farm mixes concentrate weekly and feeds the TMR twice a day out of it. Two
things have to hold for that to be recordable.

A run has to be able to be a fraction of the day. `manufacture_herd_feed` was
built on the rule that mixed feed never sits in the store — what a run produces
goes straight out — and `portion` does not break that: each half still issues
everything it made. What it must not do is drift, so the day's two halves are
asserted to reconcile against the sheet's ration exactly.

And the plan has to be read off the herds rather than typed in. The last time
it was carried by hand, the weaner herd was asking for forty-five tonnes a day.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding.concentrate_plan import concentrate_plan
from upande_livestock.serverscripts.feeding.feed_day_status import feed_day_status


class TestFeedDayStatus(IntegrationTestCase):
	HERD = "0-2"

	def setUp(self):
		if not frappe.db.exists("Herds", self.HERD):
			self.skipTest(f"{self.HERD} is not on this site")
		if not frappe.db.get_value("Herds", self.HERD, "bom"):
			self.skipTest(f"{self.HERD} has no ration")

	def test_the_day_is_head_count_times_the_ration(self):
		d = feed_day_status(self.HERD)
		self.assertTrue(d.get("ok"), d.get("error"))
		heads = flt(frappe.db.get_value("Herds", self.HERD, "number_of_animals"))
		self.assertAlmostEqual(d["day_kg"], d["per_head_kg"] * heads, places=4)

	def test_a_fresh_day_offers_half(self):
		"""Two runs a day, so the first one defaults to half of it."""
		d = feed_day_status(self.HERD)
		if d["issued_today"]:
			self.skipTest("this herd has already been fed today")
		self.assertEqual(d["suggested_portion"], 0.5)
		self.assertEqual(d["runs_done"], 0)
		self.assertFalse(d["complete"])

	def test_what_is_left_is_the_day_less_what_went_out(self):
		d = feed_day_status(self.HERD)
		self.assertAlmostEqual(
			d["remaining_kg"], max(d["day_kg"] - d["issued_kg"], 0.0), places=4
		)

	def test_the_suggestion_never_asks_for_more_than_is_left(self):
		"""A herd already fed for the day must not be offered another half."""
		d = feed_day_status(self.HERD)
		self.assertLessEqual(d["suggested_portion"] * d["day_kg"], d["remaining_kg"] + 0.01)


class TestConcentratePlan(IntegrationTestCase):
	def test_demand_is_read_off_the_herds(self):
		"""Every concentrate's daily figure is the herds that eat it, summed."""
		plan = concentrate_plan(7)
		self.assertTrue(plan.get("ok"), plan.get("error"))
		for row in plan["concentrates"]:
			expected = sum(
				flt(h["per_head_kg"]) * flt(h["heads"]) for h in row["herds"]
			)
			self.assertAlmostEqual(
				row["per_day_kg"], expected, places=2,
				msg=f"{row['item_code']} does not equal its herds' consumption",
			)

	def test_a_week_is_seven_days_of_it(self):
		plan = concentrate_plan(7)
		for row in plan["concentrates"]:
			self.assertAlmostEqual(row["needed_kg"], row["per_day_kg"] * 7, places=2)

	def test_mixing_is_rounded_up_to_whole_batches(self):
		"""The recipes are per 1000 kg; a mixer does not run a fifth of a batch."""
		plan = concentrate_plan(7)
		for row in plan["concentrates"]:
			self.assertEqual(row["to_mix_kg"], row["batches"] * plan["batch_kg"])
			self.assertGreaterEqual(
				row["to_mix_kg"] + row["on_hand_kg"] + 0.01, row["needed_kg"]
			)

	def test_nothing_is_planned_for_a_concentrate_already_covered(self):
		plan = concentrate_plan(7)
		for row in plan["concentrates"]:
			if row["on_hand_kg"] >= row["needed_kg"]:
				self.assertEqual(row["batches"], 0, f"{row['item_code']} is already covered")

	def test_a_plan_of_no_days_is_refused(self):
		result = concentrate_plan(0)
		self.assertIn("error", result)
