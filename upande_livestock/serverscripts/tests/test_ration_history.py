"""The ration record, held against this site's real feed and milk data.

The mistake worth a test of its own is the first one: reading a herd's
*current* `Herds.bom` instead of the BOM its Work Order actually used. It looks
right — the numbers line up, the page renders — and it quietly rewrites every
past day the moment somebody tunes a recipe. This site has the divergence
sitting in it (0-2 runs on BOM-TMR Calves Meal-005, standing ration -011), so
the test can be held against the real thing rather than a fixture.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, getdate

from upande_livestock.serverscripts.feeding.ration_history import ration_history


def _submitted_herd_work_orders():
	return frappe.db.sql(
		"""SELECT name, DATE(planned_start_date) AS fed_on, custom_herd AS herd,
		          bom_no, qty
		   FROM `tabWork Order`
		   WHERE IFNULL(custom_herd, '') <> '' AND docstatus = 1""",
		as_dict=True,
	)


def _milk_by_day():
	rows = frappe.db.sql(
		"""SELECT herd, recording_date, SUM(total_yield_kg) AS kg
		   FROM `tabMilk Recording` WHERE docstatus = 1
		   GROUP BY herd, recording_date""",
		as_dict=True,
	)
	return {(r.herd, getdate(r.recording_date)): flt(r.kg) for r in rows}


class TestRationHistory(IntegrationTestCase):
	def test_a_row_reports_the_bom_its_work_order_used_not_the_herds_current_one(self):
		"""The whole reason this endpoint reads Work Order.bom_no.

		0-2's standing ration is BOM-TMR Calves Meal-011; every run it has ever
		had cites -005. A history built from `Herds.bom` would report -011 for
		days that were fed -005, and would do it retroactively every time a
		recipe changes.
		"""
		divergent = [
			(h.name, h.bom, wo.bom_no)
			for h in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"])
			for wo in frappe.db.sql(
				"""SELECT DISTINCT bom_no FROM `tabWork Order`
				   WHERE custom_herd = %s AND docstatus = 1 AND bom_no <> %s""",
				(h.name, h.bom),
				as_dict=True,
			)
		]
		if not divergent:
			raise unittest.SkipTest("no herd on this site has been fed a BOM it no longer stands on")

		herd, standing, used = divergent[0]
		res = ration_history(herd=herd, limit=500)
		self.assertTrue(res.get("ok"), res.get("error"))
		self.assertTrue(res["rows"], f"expected ration rows for {herd}")

		by_wo = {}
		for wo in _submitted_herd_work_orders():
			if wo.herd == herd:
				by_wo.setdefault((getdate(wo.fed_on), wo.bom_no), []).append(wo.name)

		for row in res["rows"]:
			key = (getdate(row["fed_on"]), row["bom_no"])
			self.assertIn(
				key,
				by_wo,
				f"{row['bom_no']} on {row['fed_on']} matches no Work Order for {herd}",
			)

		reported = {r["bom_no"] for r in res["rows"]}
		self.assertIn(
			used,
			reported,
			f"{herd} was fed {used}; the history must say so, not {standing}",
		)

	def test_the_quantity_and_run_count_are_the_days_own_work_orders(self):
		"""A herd's day is mixed in more than one run, and the row has to be
		the sum of them — 0-2's calves' meal went out four times on
		2026-08-26."""
		res = ration_history(limit=1000)
		self.assertTrue(res.get("ok"), res.get("error"))
		expected = {}
		for wo in _submitted_herd_work_orders():
			key = (getdate(wo.fed_on), wo.herd, wo.bom_no)
			qty, runs = expected.get(key, (0.0, 0))
			expected[key] = (qty + flt(wo.qty), runs + 1)

		checked = 0
		for row in res["rows"]:
			key = (getdate(row["fed_on"]), row["herd"], row["bom_no"])
			self.assertIn(key, expected)
			qty, runs = expected[key]
			self.assertAlmostEqual(row["qty"], qty, places=3)
			self.assertEqual(row["runs"], runs)
			checked += 1
		self.assertGreater(checked, 0, "expected ration rows on this site")
		multi = [r for r in res["rows"] if r["runs"] > 1]
		if not multi:
			raise unittest.SkipTest("no herd-day on this site was mixed in more than one run")

	def test_each_milk_window_moves_the_figure(self):
		"""same_day, next_day, plus_two and avg_three must each read a
		different day's milk, held against a day this site actually recorded
		milk on."""
		milk = _milk_by_day()
		if not milk:
			raise unittest.SkipTest("no milk recorded on this site")

		# A ration day whose milk landed the NEXT day and not the same day —
		# the case that separates the windows instead of agreeing by accident.
		rows = ration_history(limit=1000)["rows"]
		target = None
		for row in rows:
			day = getdate(row["fed_on"])
			if (row["herd"], day) not in milk and (row["herd"], add_days(day, 1)) in milk:
				target = row
				break
		if not target:
			raise unittest.SkipTest("no ration day on this site has milk only on the day after")

		herd, day = target["herd"], getdate(target["fed_on"])
		next_kg = milk[(herd, add_days(day, 1))]

		def figure(window):
			res = ration_history(herd=herd, from_date=str(day), to_date=str(day), milk_window=window)
			self.assertTrue(res.get("ok"), res.get("error"))
			self.assertEqual(res["milk_window"], window)
			match = [r for r in res["rows"] if r["bom_no"] == target["bom_no"]]
			self.assertTrue(match, f"{target['bom_no']} vanished for window {window}")
			return match[0]["milk_kg"]

		self.assertIsNone(figure("same_day"), "nothing was recorded on the day fed")
		self.assertAlmostEqual(figure("next_day"), round(next_kg, 1), places=1)

		plus_two = milk.get((herd, add_days(day, 2)))
		self.assertEqual(
			figure("plus_two"), None if plus_two is None else round(plus_two, 1)
		)

		# The average is taken over the days actually recorded, not over three
		# regardless — recording milk on one of the three days must not report
		# a third of it.
		recorded = [
			milk[(herd, add_days(day, off))]
			for off in (0, 1, 2)
			if (herd, add_days(day, off)) in milk
		]
		self.assertAlmostEqual(
			figure("avg_three"), round(sum(recorded) / len(recorded), 1), places=1
		)

	def test_the_response_names_the_window_it_used(self):
		"""A page that prints a next-day figure under a same-day heading is
		the failure this label exists to stop."""
		for window, needle in (
			("same_day", "same day"),
			("next_day", "next day"),
			("plus_two", "two days"),
			("avg_three", "average"),
		):
			res = ration_history(limit=5, milk_window=window)
			self.assertEqual(res["milk_window"], window)
			self.assertIn(needle, res["milk_window_label"].lower())

	def test_an_unknown_window_is_refused_rather_than_quietly_defaulted(self):
		res = ration_history(limit=5, milk_window="whenever")
		self.assertIn("error", res)
		self.assertIn("whenever", res["error"])

	def test_the_herd_filter_answers_for_one_herd_only(self):
		all_rows = ration_history(limit=1000)["rows"]
		herds = sorted({r["herd"] for r in all_rows})
		self.assertGreater(len(herds), 1, "expected more than one herd in the history")
		herd = herds[0]
		res = ration_history(herd=herd, limit=1000)
		self.assertTrue(res["rows"], f"expected rows for {herd}")
		self.assertEqual({r["herd"] for r in res["rows"]}, {herd})
		self.assertEqual(
			len(res["rows"]),
			len([r for r in all_rows if r["herd"] == herd]),
		)

	def test_the_date_bounds_hold_and_a_reversed_range_is_read_forwards(self):
		rows = ration_history(limit=1000)["rows"]
		days = sorted({getdate(r["fed_on"]) for r in rows})
		self.assertGreater(len(days), 2, "expected history across several days")
		lo, hi = days[1], days[-2]

		res = ration_history(from_date=str(lo), to_date=str(hi), limit=1000)
		got = {getdate(r["fed_on"]) for r in res["rows"]}
		self.assertTrue(got, "expected rows inside the range")
		self.assertEqual(min(got), lo)
		self.assertEqual(max(got), hi)
		self.assertNotIn(days[0], got)
		self.assertNotIn(days[-1], got)

		reversed_res = ration_history(from_date=str(hi), to_date=str(lo), limit=1000)
		self.assertEqual(
			[r["fed_on"] for r in reversed_res["rows"]], [r["fed_on"] for r in res["rows"]]
		)

	def test_a_work_order_with_no_herd_is_not_a_ration_row(self):
		"""4,713 of this site's 5,168 Work Orders carry no herd — concentrate
		runs and older rows. A blank herd on this page is a row nobody can act
		on."""
		herdless_days = {
			getdate(r.fed_on)
			for r in frappe.db.sql(
				"""SELECT DISTINCT DATE(planned_start_date) AS fed_on
				   FROM `tabWork Order`
				   WHERE IFNULL(custom_herd, '') = '' AND docstatus = 1""",
				as_dict=True,
			)
		}
		with_herd_days = {getdate(r.fed_on) for r in _submitted_herd_work_orders()}
		only_herdless = sorted(herdless_days - with_herd_days)
		if not only_herdless:
			raise unittest.SkipTest("every herdless Work Order shares a day with a herd one")

		res = ration_history(limit=1000)
		self.assertTrue(all(r["herd"] for r in res["rows"]), "a row came back with no herd")

		day = only_herdless[-1]
		bounded = ration_history(from_date=str(day), to_date=str(day), limit=1000)
		self.assertEqual(
			bounded["rows"], [], f"{day} has only herdless Work Orders and must be empty"
		)

	def test_the_answer_is_bounded_and_says_when_it_was_cut_short(self):
		full = ration_history(limit=1000)
		self.assertFalse(full["truncated"])
		total = len(full["rows"])
		self.assertGreater(total, 3, "expected enough history to bound")

		cut = ration_history(limit=3)
		self.assertEqual(len(cut["rows"]), 3)
		self.assertTrue(cut["truncated"])
		# Newest first, so a bounded answer is the recent history rather than
		# an arbitrary slice of it.
		self.assertEqual([r["fed_on"] for r in cut["rows"]], [r["fed_on"] for r in full["rows"][:3]])

	def test_the_herd_filter_list_reaches_herds_that_have_since_been_renamed(self):
		"""Built from the Work Orders, not from Herds: `Bullying Heifers` owns
		rows here but is not a current herd, and a filter built from the herd
		master could not reach them."""
		res = ration_history(limit=1)
		listed = {h["herd"] for h in res["herds"]}
		fed = {r.herd for r in _submitted_herd_work_orders()}
		self.assertEqual(listed, fed)
