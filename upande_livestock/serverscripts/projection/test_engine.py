import unittest
from datetime import date

from upande_livestock.serverscripts.projection import engine as e


def animal(id_, herd, kg, adgs=(0.7, 0.95, 1.2), exit_kg=None):
	low, exp, high = adgs
	return {"id": id_, "herd": herd, "kg": kg, "adg": {"low": low, "expected": exp, "high": high}, "exit_kg": exit_kg}


class TestMeasuredAdg(unittest.TestCase):
	def test_needs_enough_weighings(self):
		pts = [(date(2026, 8, 1), 300.0)]
		self.assertIsNone(e.measured_adg(pts, 2, 30))
		self.assertIsNone(e.measured_adg([], 2, 30))

	def test_needs_enough_span(self):
		pts = [(date(2026, 10, 1), 300.0), (date(2026, 10, 15), 312.0)]
		self.assertIsNone(e.measured_adg(pts, 2, 30))

	def test_gain_over_the_whole_span(self):
		pts = [(date(2026, 8, 1), 300.0), (date(2026, 9, 1), 330.0), (date(2026, 10, 1), 360.0)]
		self.assertAlmostEqual(e.measured_adg(pts, 2, 30), 60 / 61)

	def test_unsorted_points_are_sorted(self):
		pts = [(date(2026, 10, 1), 360.0), (date(2026, 8, 1), 300.0)]
		self.assertAlmostEqual(e.measured_adg(pts, 2, 30), 60 / 61)

	def test_min_weighings_three(self):
		pts = [(date(2026, 8, 1), 300.0), (date(2026, 10, 1), 360.0)]
		self.assertIsNone(e.measured_adg(pts, 3, 30))


class TestAdgScenarios(unittest.TestCase):
	def test_measured_is_expected_and_settings_bound_it(self):
		s = e.adg_scenarios(0.95, None, True, 0.7, 1.2)
		self.assertEqual(s["source"], "measured")
		self.assertEqual((s["low"], s["expected"], s["high"]), (0.7, 0.95, 1.2))

	def test_poor_gainer_widens_the_low_end(self):
		s = e.adg_scenarios(0.4, None, True, 0.7, 1.2)
		self.assertEqual((s["low"], s["expected"], s["high"]), (0.4, 0.4, 1.2))

	def test_heavy_gainer_widens_the_high_end(self):
		s = e.adg_scenarios(1.5, None, True, 0.7, 1.2)
		self.assertEqual((s["low"], s["expected"], s["high"]), (0.7, 1.5, 1.5))

	def test_herd_target_when_not_measured(self):
		s = e.adg_scenarios(None, 0.9, True, 0.7, 1.2)
		self.assertEqual((s["expected"], s["source"]), (0.9, "herd target"))

	def test_midpoint_when_nothing_else(self):
		s = e.adg_scenarios(None, None, True, 0.7, 1.2)
		self.assertEqual((s["expected"], s["source"]), (0.95, "settings"))
		s = e.adg_scenarios(None, 0, True, 0.7, 1.2)
		self.assertEqual(s["source"], "settings")

	def test_negative_measured_is_floored_at_zero(self):
		s = e.adg_scenarios(-0.2, None, True, 0.7, 1.2)
		self.assertEqual((s["low"], s["expected"]), (0.0, 0.0))

	def test_a_herd_that_does_not_grow_stays_flat(self):
		s = e.adg_scenarios(0.9, 0.9, False, 0.7, 1.2)
		self.assertEqual((s["low"], s["expected"], s["high"], s["source"]), (0, 0, 0, "flat"))


class TestFeedAndWeights(unittest.TestCase):
	def test_daily_feed_is_a_share_of_live_weight(self):
		self.assertAlmostEqual(e.daily_feed_kg(400, 4), 16.0)
		self.assertAlmostEqual(e.daily_feed_kg(250, 4), 10.0)
		self.assertEqual(e.daily_feed_kg(0, 4), 0)

	def test_exit_day(self):
		self.assertEqual(e.exit_day(400, 1.0, 450), 50)
		self.assertEqual(e.exit_day(400, 0.95, 450), 53)       # 52.6 rounds up
		self.assertIsNone(e.exit_day(400, 0, 450))              # never at zero gain
		self.assertIsNone(e.exit_day(400, 1.0, None))           # no exit weight: stays
		self.assertEqual(e.exit_day(450, 1.0, 450), 7)          # already there: leaves within the week
		self.assertEqual(e.exit_day(470, 1.0, 450), 7)

	def test_band_of(self):
		bands = [{"herd": "Starters", "min_kg": 0, "max_kg": 250},
		         {"herd": "Growers", "min_kg": 250, "max_kg": 280},
		         {"herd": "Finishers", "min_kg": 280, "max_kg": None}]
		self.assertEqual(e.band_of(249.9, bands), "Starters")
		self.assertEqual(e.band_of(250.0, bands), "Growers")
		self.assertEqual(e.band_of(280.0, bands), "Finishers")
		self.assertEqual(e.band_of(900, bands), "Finishers")
		self.assertIsNone(e.band_of(100, []))


class TestProject(unittest.TestCase):
	def test_week_one_feed_for_a_flat_animal(self):
		out = e.project([animal("a", "Cows", 500, (0, 0, 0))], weeks=2, pct=4.0)
		w = out["total"]["expected"]["weeks"]
		self.assertEqual(len(w), 2)
		self.assertAlmostEqual(w[0]["feed_kg"], 500 * 0.04 * 7)
		self.assertAlmostEqual(w[1]["feed_kg"], 500 * 0.04 * 7)
		self.assertAlmostEqual(w[1]["cumulative_kg"], 500 * 0.04 * 14)
		self.assertEqual(w[0]["head"], 1)

	def test_growth_raises_the_feed_week_on_week(self):
		out = e.project([animal("a", "F", 300, (1.0, 1.0, 1.0))], weeks=2, pct=4.0)
		w = out["total"]["expected"]["weeks"]
		# mid-week weights: day 3.5 and day 10.5
		self.assertAlmostEqual(w[0]["feed_kg"], 0.04 * (300 + 3.5) * 7)
		self.assertAlmostEqual(w[1]["feed_kg"], 0.04 * (300 + 10.5) * 7)
		self.assertAlmostEqual(w[1]["avg_kg"], 314.0)
		self.assertAlmostEqual(w[1]["live_kg"], 314.0)

	def test_scenarios_order_low_expected_high(self):
		out = e.project([animal("a", "F", 300)], weeks=4, pct=4.0)
		lo = out["total"]["low"]["weeks"][3]
		ex = out["total"]["expected"]["weeks"][3]
		hi = out["total"]["high"]["weeks"][3]
		self.assertLess(lo["avg_kg"], ex["avg_kg"])
		self.assertLess(ex["avg_kg"], hi["avg_kg"])
		self.assertLess(lo["cumulative_kg"], hi["cumulative_kg"])

	def test_an_animal_stops_eating_when_it_leaves_at_exit_weight(self):
		# 440 kg at 1.0 -> leaves on day 10: 7 days in week one, 3 in week two
		out = e.project([animal("a", "F", 440, (1, 1, 1), exit_kg=450)], weeks=3, pct=4.0)
		w = out["total"]["expected"]["weeks"]
		self.assertEqual((w[0]["head"], w[0]["exits"]), (1, 0))
		self.assertEqual((w[1]["head"], w[1]["exits"]), (0, 1))
		self.assertAlmostEqual(w[1]["feed_kg"], 0.04 * (440 + 7 + 1.5) * 3)
		self.assertEqual(w[2]["feed_kg"], 0)
		self.assertEqual(w[2]["avg_kg"], None)

	def test_already_finished_animal_leaves_in_week_one(self):
		out = e.project([animal("a", "F", 470, (1, 1, 1), exit_kg=450)], weeks=2, pct=4.0)
		w = out["total"]["expected"]["weeks"]
		self.assertEqual((w[0]["head"], w[0]["exits"]), (0, 1))
		self.assertAlmostEqual(w[0]["feed_kg"], 0.04 * (470 + 3.5) * 7)
		self.assertEqual(w[1]["feed_kg"], 0)

	def test_per_herd_rows_add_up_to_the_total(self):
		out = e.project([animal("a", "H1", 300), animal("b", "H1", 320), animal("c", "H2", 500, (0, 0, 0))],
		                weeks=3, pct=4.0)
		for sc in ("low", "expected", "high"):
			for i in range(3):
				parts = sum(out["herds"][h][sc]["weeks"][i]["feed_kg"] for h in ("H1", "H2"))
				self.assertAlmostEqual(parts, out["total"][sc]["weeks"][i]["feed_kg"])

	def test_today_figures(self):
		out = e.project([animal("a", "H1", 300), animal("b", "H1", 200)], weeks=1, pct=4.0)
		t = out["total"]
		self.assertEqual(t["head"], 2)
		self.assertAlmostEqual(t["live_kg"], 500)
		self.assertAlmostEqual(t["day_kg"], 20.0)
		self.assertEqual(out["herds"]["H1"]["head"], 2)

	def test_band_crossings(self):
		bands = [{"herd": "Starters", "min_kg": 0, "max_kg": 250},
		         {"herd": "Growers", "min_kg": 250, "max_kg": 280},
		         {"herd": "Finishers", "min_kg": 280, "max_kg": None}]
		# 248 kg at 1.0: Growers on day 2 (week 1); Finishers on day 32 (week 5)
		out = e.project([animal("a", "Starters", 248, (1, 1, 1), exit_kg=450)], weeks=6, pct=4.0, bands=bands)
		b = out["bands"]
		self.assertEqual(b["today"], {"Starters": 1, "Growers": 0, "Finishers": 0})
		self.assertEqual(b["weeks"][0]["counts"]["Growers"], 1)
		self.assertEqual(b["weeks"][0]["moves"], [{"from": "Starters", "to": "Growers", "head": 1}])
		self.assertEqual(b["weeks"][3]["moves"], [])
		self.assertEqual(b["weeks"][4]["moves"], [{"from": "Growers", "to": "Finishers", "head": 1}])
		self.assertEqual(b["weeks"][4]["counts"]["Finishers"], 1)

	def test_band_exit_is_counted(self):
		bands = [{"herd": "Finishers", "min_kg": 0, "max_kg": None}]
		out = e.project([animal("a", "Finishers", 440, (1, 1, 1), exit_kg=450)], weeks=3, pct=4.0, bands=bands)
		self.assertEqual(out["bands"]["weeks"][1]["exits"], 1)
		self.assertEqual(out["bands"]["weeks"][1]["counts"]["Finishers"], 0)

	def test_no_bands_no_band_block(self):
		out = e.project([animal("a", "H", 300)], weeks=2, pct=4.0)
		self.assertIsNone(out["bands"])


class TestDaysOfFeed(unittest.TestCase):
	def weeks(self, *feeds):
		return [{"feed_kg": f} for f in feeds]

	def test_runs_out_inside_a_week(self):
		self.assertAlmostEqual(e.days_of_feed(150, self.weeks(100, 100, 100)), 10.5)

	def test_exactly_covers_first_week(self):
		self.assertAlmostEqual(e.days_of_feed(100, self.weeks(100, 100)), 7.0)

	def test_lasts_the_whole_horizon(self):
		self.assertIsNone(e.days_of_feed(1000, self.weeks(100, 100)))

	def test_no_stock(self):
		self.assertEqual(e.days_of_feed(0, self.weeks(100)), 0.0)

	def test_no_need_means_none(self):
		self.assertIsNone(e.days_of_feed(50, self.weeks(0, 0)))

	def test_days_at_todays_rate(self):
		self.assertAlmostEqual(e.days_at_rate(500, 50), 10.0)
		self.assertIsNone(e.days_at_rate(500, 0))


class TestSplitStock(unittest.TestCase):
	def test_central_stock_shared_by_need_plus_own_paddock_stock(self):
		got = e.split_stock(1000, {"A": 30.0, "B": 10.0}, {"A": 100.0})
		self.assertAlmostEqual(got["A"], 100 + 750)
		self.assertAlmostEqual(got["B"], 250)

	def test_no_need_no_share(self):
		self.assertEqual(e.split_stock(1000, {"A": 0, "B": 0}, {}), {"A": 0.0, "B": 0.0})


if __name__ == "__main__":
	unittest.main()
