"""The Pre-manufacture Concentrate switch, "expand into ingredients", and
Manufacture all.

Run (one run per site at a time):
    bench --site mutara.local run-tests --app upande_livestock \
        --module upande_livestock.serverscripts.tests.test_livestock_feeds
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.feeding import _concentrate as CN
from upande_livestock.serverscripts.feeding import expand_concentrate as EX
from upande_livestock.serverscripts.feeding import manufacture_all_feeds as MA
from upande_livestock.serverscripts.feeding.manufacture_concentrate import manufacture_concentrate
from upande_livestock.serverscripts.feeding.set_concentrate import set_concentrate
from upande_livestock.serverscripts.tests.test_feed_nutrition import Fake, rec

SETTING = "premanufacture_concentrate"


class TestTheSwitch(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _set(self, value):
		frappe.db.set_single_value("Livestock Settings", SETTING, value)

	def test_default_is_on(self):
		frappe.db.sql("delete from `tabSingles` where doctype='Livestock Settings' and field=%s", SETTING)
		self.assertTrue(CN.premanufacture_concentrate_on())

	def test_off_refuses_set_concentrate_with_a_clear_message(self):
		self._set(0)
		got = set_concentrate({"name": "Whatever", "lines": [{"item_code": "x", "qty": 1}]})
		self.assertIn("does not pre-manufacture", got["error"])

	def test_off_refuses_manufacture_concentrate(self):
		self._set(0)
		with patch("upande_livestock.serverscripts.feeding.manufacture_concentrate.guard_stock"):
			got = manufacture_concentrate("whatever", qty=10)
		self.assertIn("does not pre-manufacture", got["error"])

	def test_on_does_not_refuse_for_the_switch(self):
		self._set(1)
		got = set_concentrate({"name": "", "lines": []})
		self.assertNotIn("pre-manufacture", got["error"])  # fails later, for its own reason

	def test_the_setting_is_a_check_defaulting_to_on(self):
		df = frappe.get_meta("Livestock Settings").get_field(SETTING)
		self.assertEqual((df.fieldtype, str(df.default)), ("Check", "1"))


class TestExpandingAConcentrate(unittest.TestCase):
	def setUp(self):
		self.src = Fake(
			feeds={"bran": rec(90), "silage": rec(30), "hay": rec(90)},
			recipes={"meal": (10.0, [("bran", 4.0), ("silage", 6.0)], "B")},
		)

	def test_the_line_is_rewritten_from_its_bom_scaled(self):
		out, expanded = EX.expand_lines(
			[{"item_code": "meal", "qty": 5}, {"item_code": "hay", "qty": 1}],
			source=self.src, concentrates={"meal"},
		)
		self.assertEqual(expanded, ["meal"])
		self.assertEqual({r["item_code"]: r["qty"] for r in out}, {"bran": 2.0, "silage": 3.0, "hay": 1.0})

	def test_it_merges_with_a_raw_line_of_the_same_feed(self):
		out, _ = EX.expand_lines(
			[{"item_code": "meal", "qty": 10}, {"item_code": "bran", "qty": 1}],
			source=self.src, concentrates={"meal"},
		)
		self.assertEqual({r["item_code"]: r["qty"] for r in out}["bran"], 5.0)

	def test_only_concentrates_are_expanded(self):
		out, expanded = EX.expand_lines([{"item_code": "meal", "qty": 5}], source=self.src, concentrates=set())
		self.assertEqual(expanded, [])
		self.assertEqual(out[0]["item_code"], "meal")

	def test_total_weight_is_preserved(self):
		out, _ = EX.expand_lines([{"item_code": "meal", "qty": 7}], source=self.src, concentrates={"meal"})
		self.assertAlmostEqual(sum(r["qty"] for r in out), 7)


class TestManufactureAll(IntegrationTestCase):
	"""Which herds it runs, and that it only ever runs the rest of a day."""

	def setUp(self):
		self.herds = [h for h in frappe.get_all("Herds", fields=["name", "bom"]) if h.bom]
		if len(self.herds) < 3:
			self.skipTest("needs three herds with rations (seed_mutara_beef)")
		self.fed_herd, self.half_herd, self.fresh = (h.name for h in self.herds[:3])
		self.other = [h.name for h in self.herds[3:]]
		self.day_qty = {}

	def tearDown(self):
		frappe.db.rollback()

	def _issues(self, item, herd, day):
		from upande_livestock.serverscripts.common.calf_separation import fed_head_count

		bom = frappe.db.get_value("Herds", herd, "bom")
		per_head = frappe.db.get_value("BOM", bom, "quantity")
		full = per_head * fed_head_count(herd)
		if herd == self.fed_herd:
			return [frappe._dict(qty=full)]
		if herd == self.half_herd:
			return [frappe._dict(qty=full / 2)]
		return []

	def _preview(self):
		with patch("upande_livestock.serverscripts.feeding.feed_day_status._issues_on", self._issues), patch.object(
			MA, "guard_stock"
		), patch.object(MA, "_plan_concentrates", return_value=[]):
			return MA.manufacture_all_feeds(preview=1)

	def test_a_fully_fed_herd_is_skipped(self):
		got = self._preview()
		self.assertTrue(got["ok"], got)
		self.assertIn((self.fed_herd, "already fully fed"), [(s["herd"], s["reason"]) for s in got["skipped"]])
		self.assertNotIn(self.fed_herd, [r["herd"] for r in got["herds"]])

	def test_a_part_fed_herd_runs_only_what_is_left(self):
		got = self._preview()
		half = next(r for r in got["herds"] if r["herd"] == self.half_herd)
		self.assertAlmostEqual(half["portion"], 0.5, places=3)

	def test_a_fresh_herd_runs_the_whole_day(self):
		got = self._preview()
		fresh = next(r for r in got["herds"] if r["herd"] == self.fresh)
		self.assertEqual(fresh["portion"], 1.0)

	def test_preview_writes_nothing(self):
		with patch.object(MA.feeding, "manufacture_herd_feed") as made:
			self._preview()
		made.assert_not_called()

	def test_running_calls_the_engine_once_per_herd_that_needs_feeding(self):
		calls = []

		def engine(herd, **kw):
			calls.append((herd, kw["portion"]))
			return {"work_order": "WO-" + herd, "produced_qty": 1, "issued_qty": 1, "uom": "Kg"}

		with patch("upande_livestock.serverscripts.feeding.feed_day_status._issues_on", self._issues), patch.object(
			MA, "guard_stock"
		), patch.object(MA, "_plan_concentrates", return_value=[]), patch.object(
			MA.feeding, "manufacture_herd_feed", engine
		):
			got = MA.manufacture_all_feeds()
		self.assertTrue(got["ok"], got)
		ran = [c[0] for c in calls]
		self.assertNotIn(self.fed_herd, ran)
		self.assertIn(self.half_herd, ran)
		self.assertEqual(sorted(ran), sorted([self.half_herd, self.fresh, *self.other_with_heads()]))

	def other_with_heads(self):
		from upande_livestock.serverscripts.common.calf_separation import fed_head_count

		return [h for h in self.other if fed_head_count(h) > 0]

	def test_one_herd_failing_does_not_stop_the_others(self):
		def engine(herd, **kw):
			if herd == self.fresh:
				frappe.throw("no operator")
			return {"work_order": "WO", "produced_qty": 1, "issued_qty": 1}

		with patch("upande_livestock.serverscripts.feeding.feed_day_status._issues_on", self._issues), patch.object(
			MA, "guard_stock"
		), patch.object(MA, "_plan_concentrates", return_value=[]), patch.object(
			MA.feeding, "manufacture_herd_feed", engine
		):
			got = MA.manufacture_all_feeds()
		by = {r["herd"]: r for r in got["herds"]}
		self.assertEqual(by[self.fresh]["status"], "error")
		self.assertEqual(by[self.half_herd]["status"], "made")

	def test_with_the_switch_off_no_concentrate_is_planned(self):
		frappe.db.set_single_value("Livestock Settings", SETTING, 0)
		with patch("upande_livestock.serverscripts.feeding.feed_day_status._issues_on", self._issues), patch.object(
			MA, "guard_stock"
		), patch.object(MA, "_plan_concentrates") as planned:
			got = MA.manufacture_all_feeds(preview=1)
		planned.assert_not_called()
		self.assertEqual(got["concentrates"], [])
		self.assertFalse(got["premanufacture_concentrate"])
