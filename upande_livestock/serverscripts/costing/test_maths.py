"""The cost-per-animal arithmetic, without a site.

Runs under bench (`bench run-tests --module ...costing.test_maths`) or plain
`python -m unittest`, since `_maths` imports nothing from frappe.
"""

import unittest
from datetime import date

from upande_livestock.serverscripts.costing import _maths as m

D1, D2, D3 = date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)


class TestLabour(unittest.TestCase):
	RATES = {"Feedlot workers": 400, "Herders": 400, "Other": 350}

	def test_blank_or_zero_rate_takes_the_default(self):
		out = m.labour_lines(
			[{"category": "Feedlot workers", "workers": 6}, {"category": "Other", "workers": 1, "day_rate": 0}],
			self.RATES,
		)
		self.assertEqual([(r["day_rate"], r["amount"]) for r in out], [(400, 2400), (350, 350)])

	def test_a_typed_rate_wins(self):
		out = m.labour_lines([{"category": "Herders", "workers": 3, "day_rate": "500"}], self.RATES)
		self.assertEqual(out[0]["amount"], 1500)

	def test_rows_without_workers_are_dropped(self):
		self.assertEqual(m.labour_lines([{"category": "Herders", "workers": 0}], self.RATES), [])

	def test_bad_rows_are_refused(self):
		with self.assertRaises(ValueError):
			m.labour_lines([{"category": "Cooks", "workers": 1}], self.RATES)
		with self.assertRaises(ValueError):
			m.labour_lines([{"category": "Herders", "workers": -1}], self.RATES)
		with self.assertRaises(ValueError):
			m.labour_lines([{"category": "Herders", "workers": 1, "day_rate": -5}], self.RATES)


class TestPresence(unittest.TestCase):
	def test_arrival_counts_departure_does_not(self):
		days = m.days_between(D1, D3)
		out = m.count_present(days, [(D2, None), (date(2026, 1, 1), D3), (D3, D3)])
		self.assertEqual(out, {D1: 1, D2: 2, D3: 1})

	def test_stays_outside_the_window_count_nothing(self):
		days = m.days_between(D1, D2)
		self.assertEqual(m.count_present(days, [(date(2026, 1, 1), D1), (D3, None)]), {D1: 0, D2: 0})

	def test_clip_to_exit(self):
		self.assertEqual(m.clip_stay(D1, None, D2), (D1, D2))
		self.assertEqual(m.clip_stay(D1, D2, D3), (D1, D2))
		self.assertEqual(m.clip_stay(D1, D3, None), (D1, D3))

	def test_replay_by_number(self):
		apply = lambda s, ev: {"n": ev["n"]} if ev["t"] == "count" else {"n": s["n"] + ev["n"]}
		events = [{"event_date": "2026-10-30", "t": "count", "n": 10}, {"event_date": "2026-11-02", "t": "add", "n": -3}]
		out = m.replay_heads(m.days_between(D1, D3), events, apply, lambda: {"n": 0}, lambda s: s["n"])
		self.assertEqual(out, {D1: 10, D2: 7, D3: 7})


class TestRemarks(unittest.TestCase):
	def test_longest_herd_with_the_separator_wins(self):
		herds = ["Group 1", "Group 1 - Finishers", "0-2", "10-2"]
		self.assertEqual(m.herd_of_feed("Animal feeding - Group 1 - Finishers - TMR - 10 kg", herds), "Group 1 - Finishers")
		self.assertEqual(m.herd_of_feed("Animal feeding - Group 1 - TMR - 10 kg", herds), "Group 1")
		self.assertEqual(m.herd_of_feed("Animal feeding - 10-2 - TMR - 1 kg", herds), "10-2")
		self.assertIsNone(m.herd_of_feed("Drug issue", herds))

	def test_fed_day(self):
		self.assertEqual(m.fed_day("Animal feeding - A - X - 1 kg - fed 2026-11-01", "2026-11-04"), D1)
		self.assertEqual(m.fed_day("Animal feeding - A - X - 1 kg", "2026-11-04"), date(2026, 11, 4))


class TestReport(unittest.TestCase):
	def test_spread_over_every_animal_feed_per_herd(self):
		days = [D1, D2]
		out = m.build_report(
			days,
			feed={D1: 1000, D2: 0},
			medicine={D1: 100},
			labour={D1: 2400, D2: 2400},
			fuel={D2: 500},
			animals={D1: 100, D2: 0},
			herd_feed={"Finishers": {D1: 1000}},
			herd_heads={"Finishers": {D1: 40, D2: 40}, "Empty": {}},
		)
		d1, d2 = out["days"]
		self.assertEqual(d1["total_cost"], 3500)
		self.assertEqual(d1["cost_per_animal"], 35)
		# No animals: no figure, not a zero and not a division error.
		self.assertIsNone(d2["cost_per_animal"])
		self.assertEqual(out["months"][0]["total_cost"], 6400)
		self.assertEqual(out["months"][0]["animal_days"], 100)
		self.assertEqual(out["months"][0]["cost_per_animal"], 64)
		self.assertEqual([h["herd"] for h in out["herds"]], ["Finishers"])
		self.assertEqual(out["herds"][0]["feed_cost_per_head_day"], 12.5)
		self.assertEqual(out["herds"][0]["days"][0]["feed_cost_per_head"], 25)
		self.assertEqual(out["total"]["total_cost"], 6400)

	def test_months_split(self):
		days = m.days_between("2026-10-31", "2026-11-01")
		out = m.build_report(days, {}, {}, {d: 10 for d in days}, {}, {d: 1 for d in days}, {}, {})
		self.assertEqual([x["month"] for x in out["months"]], ["2026-10", "2026-11"])


if __name__ == "__main__":
	unittest.main()
