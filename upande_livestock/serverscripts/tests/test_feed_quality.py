# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Quality & Feed: each milking herd's lab figures beside its ration, and
against the other milking herds together."""

import unittest
from types import SimpleNamespace as R
from unittest.mock import patch

from upande_livestock.serverscripts.quality import _feed_quality as FQ


def _rec(day, cows, kg, fat, protein, scc):
	return R(recording_date=day, cows_milked=cows, net_yield_kg=kg, fat_percent=fat,
	         protein_percent=protein, bulk_scc=scc)


MILK = {
	"A": [_rec("2026-10-05", 10, 100, 3.6, 3.2, 250000), _rec("2026-10-05", 10, 80, 3.8, 3.2, 250000),
	      _rec("2026-10-06", 10, 90, 3.7, 3.2, 250000)],
	"B": [_rec("2026-10-05", 20, 200, 3.6, 3.2, 250000)],
	"T": [_rec("2026-10-06", 5, 40, 4.4, 3.4, 150000), _rec("2026-10-06", 5, 0, 0, 0, 0)],
}


class TestFeedQuality(unittest.TestCase):
	def _run(self, days=90):
		with patch.object(FQ, "milking_herds", return_value=["A", "B", "T"]), \
		     patch.object(FQ, "_milk", side_effect=lambda h, s, e: MILK[h]), \
		     patch.object(FQ, "_ration", return_value=None), \
		     patch.object(FQ, "_fed", return_value={"runs": 0, "kg": 0}), \
		     patch.object(FQ.frappe.db, "count", return_value=10):
			return FQ.feed_quality(days)

	def test_figures_are_the_mean_of_the_milkings_that_have_them(self):
		t = next(h for h in self._run()["herds"] if h["herd"] == "T")
		# The empty milking has no lab figures and must not drag the mean down.
		self.assertAlmostEqual(t["quality"]["fat"], 4.4)
		self.assertEqual(t["quality"]["readings"], 1)
		self.assertEqual(t["quality"]["milkings"], 2)

	def test_milk_a_cow_a_day_counts_each_day_once(self):
		a = next(h for h in self._run()["herds"] if h["herd"] == "A")
		# 270 kg over two days of ten cows (the morning and evening are one day).
		self.assertAlmostEqual(a["quality"]["milk_per_cow_day"], 13.5)

	def test_a_herd_is_set_against_the_others_together(self):
		t = next(h for h in self._run()["herds"] if h["herd"] == "T")
		others = (3.7 + 3.6) / 2  # A's mean, then B's
		self.assertAlmostEqual(t["vs_rest"]["fat"], round((4.4 / others - 1) * 100, 1))
		self.assertLess(t["vs_rest"]["scc"], 0)

	def test_weeks_group_by_monday(self):
		out = self._run()
		self.assertEqual([w["week"] for w in out["weeks"]], ["2026-10-05"])
		self.assertEqual(set(out["weeks"][0]["herds"]), {"A", "B", "T"})

	def test_an_unknown_window_falls_back_to_ninety_days(self):
		self.assertEqual(self._run(days=7)["days"], 90)
		self.assertEqual(self._run(days=150)["days"], 150)


class TestTheEndpointIsGuarded(unittest.TestCase):
	def test_it_asks_to_read_milk_recordings(self):
		from upande_livestock.serverscripts.quality import quality_vs_feed as E

		with patch.object(E, "guard_read") as guard, patch.object(E, "feed_quality", return_value={}):
			out = E.quality_vs_feed({"days": 30})
		guard.assert_called_once_with("Milk Recording")
		self.assertTrue(out["ok"])
