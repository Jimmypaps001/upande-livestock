# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Milking dashboard charts: milk_by_herd and quality_trend."""

import unittest
from datetime import date

from upande_livestock.serverscripts.milking import milk_by_herd as M
from upande_livestock.serverscripts.quality import quality_trend as Q


def _r(herd, day, kg, cows):
	return {"herd": herd, "recording_date": day, "net_yield_kg": kg, "cows_milked": cows}


class TestMilkByHerd(unittest.TestCase):
	def test_one_series_per_herd_over_every_day(self):
		out = M.build([_r("A", "2026-11-01", 100, 10), _r("B", "2026-11-03", 50, 5)],
		              date(2026, 11, 1), date(2026, 11, 3))
		self.assertEqual(out["days"], ["2026-11-01", "2026-11-02", "2026-11-03"])
		self.assertEqual([s["herd"] for s in out["herds"]], ["A", "B"])
		self.assertEqual(out["herds"][0]["kg"], [100, 0, 0])
		self.assertEqual(out["herds"][1]["kg"], [0, 0, 50])

	def test_per_cow_uses_the_larger_milking_not_the_sum_of_cows(self):
		out = M.build([_r("A", "2026-11-01", 60, 10), _r("A", "2026-11-01", 40, 10)],
		              date(2026, 11, 1), date(2026, 11, 1))
		a = out["herds"][0]
		self.assertEqual(a["kg"], [100])
		self.assertEqual(a["per_cow"], [10.0])

	def test_a_day_without_milking_has_no_per_cow(self):
		out = M.build([_r("A", "2026-11-01", 10, 2)], date(2026, 11, 1), date(2026, 11, 2))
		self.assertEqual(out["herds"][0]["per_cow"], [5.0, None])

	def test_window_defaults_and_clamps(self):
		s, e = M.window("2026-01-01", "2026-11-01")
		self.assertEqual((e - s).days, M.MAX_DAYS - 1)
		s, e = M.window("2026-11-05", "2026-11-01")
		self.assertLess(s, e)


class TestQualityTrend(unittest.TestCase):
	def test_missing_figures_are_none_and_result_defaults(self):
		out = Q.build([{"name": "T1", "sample_date": "2026-11-01", "shift": "Morning",
		                "butterfat_percent": 3.8, "protein_percent": 0, "snf_percent": 8.5,
		                "overall_result": "Fail"},
		               {"name": "T2", "sample_date": "2026-11-02"}])
		self.assertEqual(out[0]["fat"], 3.8)
		self.assertIsNone(out[0]["protein"])
		self.assertEqual(out[0]["result"], "Fail")
		self.assertEqual(out[1]["result"], "Not assessed")
		self.assertIsNone(out[1]["fat"])
