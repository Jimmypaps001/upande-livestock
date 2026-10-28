import unittest
from datetime import date

from upande_livestock.serverscripts.forecast import engine as e


class TestEngine(unittest.TestCase):
	def test_iso_week_start_monday(self):
		self.assertEqual(e.iso_week_start(date(2026, 10, 28)), date(2026, 10, 26))
		self.assertEqual(e.iso_week_start(date(2026, 10, 26)), date(2026, 10, 26))
		self.assertEqual(e.iso_week_start(date(2026, 11, 1)), date(2026, 10, 26))

	def test_forecast_adg_fallback_chain(self):
		self.assertEqual(e.forecast_adg(0.9, 0.8, 0.7, 0.6), (0.9, "own"))
		self.assertEqual(e.forecast_adg(None, 0.8, 0.7, 0.6), (0.8, "herd"))
		self.assertEqual(e.forecast_adg(0, 0.8, 0.7, 0.6), (0.8, "herd"))
		self.assertEqual(e.forecast_adg(-1, -2, 0.7, 0.6), (0.7, "herd_target"))
		self.assertEqual(e.forecast_adg(None, None, 0, 0.6), (0.6, "farm_target"))
		self.assertEqual(e.forecast_adg(None, None, None, None), (None, "none"))
		self.assertEqual(e.forecast_adg(-1, 0, -3, 0), (None, "none"))

	def test_ready_date_basic(self):
		self.assertEqual(e.ready_date(400, date(2026, 10, 1), 1.0, 450, date(2026, 10, 1)), date(2026, 11, 20))

	def test_ready_date_never_before_today(self):
		self.assertEqual(e.ready_date(400, date(2026, 10, 1), 1.0, 450, date(2026, 12, 1)), date(2026, 12, 1))

	def test_ready_date_already_heavy_is_today(self):
		self.assertEqual(e.ready_date(460, date(2026, 9, 1), 0.5, 450, date(2026, 10, 28)), date(2026, 10, 28))
		self.assertEqual(e.ready_date(460, date(2026, 9, 1), None, 450, date(2026, 10, 28)), date(2026, 10, 28))

	def test_ready_date_losing_weight_is_none(self):
		self.assertIsNone(e.ready_date(400, date(2026, 10, 1), -0.2, 450, date(2026, 10, 28)))
		self.assertIsNone(e.ready_date(400, date(2026, 10, 1), 0, 450, date(2026, 10, 28)))
		self.assertIsNone(e.ready_date(400, date(2026, 10, 1), None, 450, date(2026, 10, 28)))

	def test_project_weight(self):
		self.assertEqual(e.project_weight(400, date(2026, 10, 1), 1.0, date(2026, 10, 11)), 410)

	def test_weekly_output_buckets_and_horizon(self):
		today = date(2026, 10, 28)  # week starts Oct 26
		bulls = [
			dict(animal="A", herd="H", latest_kg=449, latest_date=today, adg=1.0, exit_kg=450),  # Oct 29, wk0
			dict(animal="B", herd="H", latest_kg=460, latest_date=today, adg=1.0, exit_kg=450),  # today, wk0
			dict(animal="C", herd="H", latest_kg=440, latest_date=today, adg=1.0, exit_kg=450),  # Nov 7, wk1
			dict(animal="D", herd="H", latest_kg=100, latest_date=today, adg=1.0, exit_kg=450),  # beyond
			dict(animal="E", herd="H", latest_kg=400, latest_date=today, adg=None, exit_kg=450),  # never
		]
		out = e.weekly_output(bulls, today, 2)
		self.assertEqual([r["week_start"] for r in out], [date(2026, 10, 26), date(2026, 11, 2)])
		self.assertEqual(out[0]["head"], 2)
		self.assertEqual(out[0]["animals"], ["A", "B"])
		self.assertEqual(out[0]["kg"], 910.0)  # A projected 450, B stays 460
		self.assertEqual(out[1]["head"], 1)
		self.assertEqual(out[1]["kg"], 450.0)

	def test_cover_gap_and_carry(self):
		w1, w2 = date(2026, 10, 26), date(2026, 11, 2)
		output = [dict(week_start=w1, head=5, kg=2250.0, animals=[]), dict(week_start=w2, head=0, kg=0.0, animals=[])]
		commitments = [
			dict(week_start=w1, head=2, kg=900), dict(week_start=w1, head=1, kg=None),
			dict(week_start=w2, head=4, kg=None),
		]
		rows = e.cover(output, commitments)
		self.assertEqual(rows[0]["committed_head"], 3)
		self.assertEqual(rows[0]["committed_kg"], 900)
		self.assertEqual(rows[0]["balance_head"], 2)
		self.assertEqual(rows[0]["status"], "Surplus")
		self.assertEqual(rows[1]["carry_in_head"], 2)
		self.assertEqual(rows[1]["available_head"], 2)
		self.assertEqual(rows[1]["balance_head"], -2)
		self.assertEqual(rows[1]["status"], "Gap")

	def test_cover_covered_and_idle(self):
		w1, w2 = date(2026, 10, 26), date(2026, 11, 2)
		output = [dict(week_start=w1, head=3, kg=1.0, animals=[]), dict(week_start=w2, head=0, kg=0.0, animals=[])]
		rows = e.cover(output, [dict(week_start=w1, head=3, kg=None)])
		self.assertEqual(rows[0]["status"], "Covered")
		self.assertEqual(rows[1]["status"], "Idle")
		self.assertEqual(rows[1]["balance_head"], 0)

	def test_error_pct_zero_forecast_none(self):
		self.assertIsNone(e.error_pct(10, 0))
		self.assertIsNone(e.error_pct(10, None))
		self.assertIsNone(e.error_pct(None, 10))
		self.assertEqual(e.error_pct(110, 100), 0.1)
		self.assertEqual(e.error_pct(1, 3), -0.6667)

	def test_trend_buckets_interval_adg(self):
		today = date(2026, 10, 28)
		pts = [("A", "H1", date(2026, 9, 28), 400.0), ("A", "H1", date(2026, 10, 28), 430.0)]
		rows = e.trend_buckets(pts, today, 4)
		wk = date(2026, 10, 26)
		herd = [r for r in rows if r["herd"] == "H1" and r["week_start"] == wk]
		farm = [r for r in rows if r["herd"] == "__farm__" and r["week_start"] == wk]
		self.assertEqual(len(herd), 1)
		self.assertEqual(herd[0]["avg_adg"], 1.0)
		self.assertEqual(herd[0]["head"], 1)
		self.assertEqual(herd[0]["avg_weight"], 430.0)
		self.assertEqual(farm[0]["avg_adg"], 1.0)
		self.assertEqual(len(rows), 2)

	def test_trend_buckets_window_excludes_old(self):
		today = date(2026, 10, 28)
		pts = [("A", "H1", date(2025, 1, 1), 300.0), ("A", "H1", date(2025, 1, 31), 330.0)]
		self.assertEqual(e.trend_buckets(pts, today, 4), [])


if __name__ == "__main__":
	unittest.main()
