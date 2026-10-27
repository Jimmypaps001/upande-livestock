"""The ration record, held against this site's real feed data.

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
from frappe.utils import add_days, flt, getdate, today

from upande_livestock.serverscripts.feeding.ration_history import ration_history
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, submit_weight


def _submitted_herd_work_orders():
	return frappe.db.sql(
		"""SELECT name, DATE(planned_start_date) AS fed_on, custom_herd AS herd,
		          bom_no, qty
		   FROM `tabWork Order`
		   WHERE IFNULL(custom_herd, '') <> '' AND docstatus = 1""",
		as_dict=True,
	)


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


# Hay on this site: written in kg on every herd BOM, stocked in BALE at a
# conversion factor of 0.07. The item that makes "recipe units, not stock
# units" a fourteen-fold error rather than a pedantic one.
HAY = "4040010034"


class TestRationHistoryCarriesTheRecipeLines(IntegrationTestCase):
	"""An operator opening a day wants to know what went in the mixer.

	The lines have to be the recipe's own — `BOM Item.qty`/`.uom` — because
	the stock figure for hay is a fourteenth of the kilograms anybody weighed.
	"""

	def test_every_row_carries_the_lines_of_the_bom_it_cites(self):
		res = ration_history(limit=50)
		self.assertTrue(res.get("ok"), res.get("error"))
		self.assertTrue(res["rows"], "expected ration history on this site")
		for row in res["rows"]:
			expected = frappe.get_all(
				"BOM Item",
				filters={"parent": row["bom_no"], "parenttype": "BOM"},
				fields=["item_code"],
				order_by="idx asc",
			)
			self.assertEqual(
				[ln["item_code"] for ln in row["lines"]],
				[r.item_code for r in expected],
				f"{row['fed_on']} {row['herd']} cites {row['bom_no']}",
			)

	def test_hay_comes_back_in_kilograms_not_bales(self):
		rows = ration_history(limit=200)["rows"]
		checked = 0
		for row in rows:
			recipe = {
				r.item_code: r
				for r in frappe.get_all(
					"BOM Item",
					filters={"parent": row["bom_no"], "parenttype": "BOM", "item_code": HAY},
					fields=["item_code", "qty", "uom", "stock_qty", "stock_uom"],
				)
			}
			if HAY not in recipe:
				continue
			hay = recipe[HAY]
			if hay.uom == hay.stock_uom:
				continue
			line = next(ln for ln in row["lines"] if ln["item_code"] == HAY)
			self.assertEqual(line["uom"], hay.uom)
			self.assertAlmostEqual(flt(line["qty"]), flt(hay.qty), places=4)
			self.assertNotAlmostEqual(flt(line["qty"]), flt(hay.stock_qty), places=4)
			checked += 1
		if not checked:
			raise unittest.SkipTest("no row in the recent history carries hay in a non-stock UOM")


def _fed(herd, day, bom="ZZ-BOM-A", qty=100):
	"""A submitted Work Order row, written directly: a real one needs an item,
	a BOM and warehouses, none of which this page reads beyond these columns."""
	name = "ZZ-WO-" + frappe.generate_hash(length=8)
	now = frappe.utils.now()
	frappe.db.sql(
		"""INSERT INTO `tabWork Order`
		   (name, creation, modified, owner, modified_by, docstatus, custom_herd,
		    planned_start_date, bom_no, production_item, qty, custom_no_of_cows)
		   VALUES (%s, %s, %s, 'Administrator', 'Administrator', 1, %s, %s, %s, 'ZZ-ITEM', %s, 5)""",
		(name, now, now, herd, f"{day} 08:00:00", bom, qty),
	)


class TestRationHistoryShowsGain(IntegrationTestCase):
	def setUp(self):
		isolate(self)

	def _row(self, herd, day):
		res = ration_history(herd=herd, limit=50)
		self.assertTrue(res.get("ok"), res.get("error"))
		return next(r for r in res["rows"] if r["fed_on"] == str(day))

	def test_period_shows_herd_gain(self):
		herd = make_herd("ZZ Ration Gain", "Fattening").name
		a = make_animal(herd)
		b = make_animal(herd)
		make_animal(herd, 300)  # weighed once: not counted
		submit_weight(a.name, 200, days_ago=30)
		submit_weight(a.name, 230, days_ago=0)  # 1.0
		submit_weight(b.name, 200, days_ago=30)
		submit_weight(b.name, 218, days_ago=0)  # 0.6
		for ago in (30, 15, 0):
			_fed(herd, add_days(today(), -ago))
		row = self._row(herd, add_days(today(), -15))
		self.assertAlmostEqual(row["avg_adg_kg"], 0.8, places=3)
		self.assertEqual(row["weighed_head"], 2)

	def test_period_ends_where_the_recipe_changes(self):
		herd = make_herd("ZZ Ration Switch", "Fattening").name
		a = make_animal(herd)
		submit_weight(a.name, 200, days_ago=40)
		submit_weight(a.name, 220, days_ago=20)  # 1.0 across the first recipe
		submit_weight(a.name, 280, days_ago=0)
		_fed(herd, add_days(today(), -40), "ZZ-BOM-A")
		_fed(herd, add_days(today(), -20), "ZZ-BOM-A")
		_fed(herd, add_days(today(), -19), "ZZ-BOM-B")
		_fed(herd, today(), "ZZ-BOM-B")
		self.assertAlmostEqual(self._row(herd, add_days(today(), -40))["avg_adg_kg"], 1.0, places=3)
		# Second recipe: only the 20-days-ago weighing is outside it, so one point.
		late = self._row(herd, today())
		self.assertIsNone(late["avg_adg_kg"])
		self.assertEqual(late["weighed_head"], 0)
