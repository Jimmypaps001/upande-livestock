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


class TestHistory(unittest.TestCase):
	STOCK = {"Finishers": {D1: 900.0, D2: 0.0}}
	HISTORY = {
		"Finishers": {D1: {"cost": 5000, "heads": 100}, D2: {"cost": 4000, "heads": 100},
		              D3: {"cost": 3000, "heads": 60}},
		"Growers": {"2026-11-02": {"cost": 1000, "heads": 50}},
	}

	def test_history_only_where_the_ledger_has_nothing(self):
		feed, hist = m.merge_feed(self.STOCK, self.HISTORY)
		# D1 and D2 have a ledger issue (D2's valued at nothing): the ledger's, never both.
		self.assertEqual(feed["Finishers"], {D1: 900.0, D2: 0.0, D3: 3000.0})
		self.assertEqual(hist["Finishers"], {D3: 60})
		# A herd with no ledger feed at all, keyed by an ISO string, still lands on its day.
		self.assertEqual(feed["Growers"], {D2: 1000.0})
		self.assertEqual(hist["Growers"], {D2: 50})

	def test_inputs_are_not_changed(self):
		stock = {"Finishers": {D1: 1.0}}
		m.merge_feed(stock, {"Finishers": {D2: {"cost": 2, "heads": 1}}})
		self.assertEqual(stock, {"Finishers": {D1: 1.0}})

	def test_history_heads_replace_the_herds_on_those_days(self):
		heads = m.with_history_heads({"Finishers": {D1: 200, D3: 200}}, {"Finishers": {D3: 60}, "Growers": {D2: 0}})
		self.assertEqual(heads["Finishers"], {D1: 200, D3: 60})
		# No head on the history row: nothing to put in, not a zero over the app's count.
		self.assertEqual(heads["Growers"], {})

	def test_report_marks_history_days(self):
		days = [D2, D3]
		feed, hist = m.merge_feed(self.STOCK, self.HISTORY)
		heads = m.with_history_heads({"Finishers": {D2: 200, D3: 200}}, hist)
		out = m.build_report(
			days,
			feed={d: sum(h.get(d, 0) for h in feed.values()) for d in days},
			medicine={}, labour={}, fuel={}, animals={D2: 250, D3: 250},
			herd_feed=feed, herd_heads=heads, from_history=hist,
		)
		d2, d3 = out["days"]
		self.assertEqual((d2["feed_cost"], d2["history_feed_cost"], d2["feed_from_history"]), (1000, 1000, True))
		self.assertEqual((d3["feed_cost"], d3["history_feed_cost"], d3["feed_from_history"]), (3000, 3000, True))
		self.assertEqual(out["total"]["history_feed_cost"], 4000)
		self.assertEqual(out["months"][0]["history_feed_cost"], 4000)
		fin = next(h for h in out["herds"] if h["herd"] == "Finishers")
		self.assertEqual((fin["history_days"], fin["history_feed_cost"]), (1, 3000))
		# D3 is costed over the tracker's 60 head, not the 200 the app holds today.
		self.assertEqual([(x["date"], x["heads"], x["from_history"]) for x in fin["days"]],
		                 [("2026-11-02", 200, False), ("2026-11-03", 60, True)])
		self.assertEqual(fin["days"][1]["feed_cost_per_head"], 50)

	def test_no_history_marks_nothing(self):
		out = m.build_report([D1], {D1: 10}, {}, {}, {}, {D1: 1}, {"A": {D1: 10}}, {"A": {D1: 1}})
		self.assertFalse(out["days"][0]["feed_from_history"])
		self.assertEqual(out["herds"][0]["history_days"], 0)


if __name__ == "__main__":
	unittest.main()
