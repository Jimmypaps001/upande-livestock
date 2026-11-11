# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Feeding the way Mutara feeds: typed group totals, a concentrate switch per
herd, per-head doses, and interchangeable forage.

The pure classes need no site:
    cd sites && ../env/bin/python -m unittest \
        upande_livestock.serverscripts.tests.test_feeding_the_mutara_way

The Integration classes need one (one run per site at a time):
    bench --site mutara.local run-tests --app upande_livestock \
        --module upande_livestock.serverscripts.tests.test_feeding_the_mutara_way
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.feeding import _concentrate as CN
from upande_livestock.serverscripts.feeding import _doses as DO
from upande_livestock.serverscripts.feeding import _head_count as HC
from upande_livestock.serverscripts.feeding import _tuned_bom as TB
from upande_livestock.serverscripts.feeding import expand_concentrate as EX
from upande_livestock.serverscripts.feeding import feed_nutrition as FN
from upande_livestock.serverscripts.feeding import feed_substitutes as FS
from upande_livestock.serverscripts.feeding import manufacture_all_feeds as MA

# ── Pure ─────────────────────────────────────────────────────────────────────


class TestTypedTotals(unittest.TestCase):
	def test_the_suggestion_is_head_count_times_per_head(self):
		self.assertEqual(HC.suggested_total(20, 40), 800)
		self.assertEqual(HC.suggested_total(20, 40, 0.5), 400)

	def test_a_typed_total_is_recorded_as_a_share_of_the_head_count_day(self):
		self.assertAlmostEqual(HC.portion_for_total(20, 40, 600), 0.75)

	def test_more_than_the_suggestion_is_not_capped(self):
		self.assertAlmostEqual(HC.portion_for_total(20, 40, 1000), 1.25)

	def test_no_head_count_day_gives_no_share(self):
		self.assertEqual(HC.portion_for_total(0, 40, 600), 0.0)

	def test_a_blank_or_zero_total_is_no_total(self):
		for raw in (None, "", 0, "0", -5):
			self.assertIsNone(HC.clean_total(raw))
		self.assertEqual(HC.clean_total("612.5"), 612.5)


class TestHerdConcentrateMode(unittest.TestCase):
	def test_explicit_answers_win_over_the_farm(self):
		self.assertTrue(CN.resolve_premanufacture(CN.PRE_MANUFACTURE, False))
		self.assertFalse(CN.resolve_premanufacture(CN.MIX_FROM_RAW, True))

	def test_farm_default_and_blank_follow_the_farm(self):
		for mode in (CN.FARM_DEFAULT, None, ""):
			self.assertTrue(CN.resolve_premanufacture(mode, True))
			self.assertFalse(CN.resolve_premanufacture(mode, False))


class TestDoses(unittest.TestCase):
	def test_grams_and_millilitres_are_doses_kilos_are_not(self):
		self.assertTrue(DO.is_dose("Gram"))
		self.assertTrue(DO.is_dose("Millilitre"))
		for uom in ("Kilogram", "BALE", None, ""):
			self.assertFalse(DO.is_dose(uom))

	def test_si_factor_between_units_of_one_kind(self):
		self.assertAlmostEqual(DO.si_factor("Gram", "Kilogram"), 0.001)
		self.assertAlmostEqual(DO.si_factor("Gram", "Kg"), 0.001)
		self.assertAlmostEqual(DO.si_factor("Millilitre", "Litre"), 0.001)
		self.assertEqual(DO.si_factor("Gram", "Gram"), 1.0)

	def test_no_factor_across_kinds_or_for_packs(self):
		self.assertIsNone(DO.si_factor("Gram", "Litre"))
		self.assertIsNone(DO.si_factor("Millilitre", "BAG"))

	def test_the_items_own_conversion_comes_first(self):
		# A 25 kg bag of Meat Boost: one gram is 1/25000 of a bag.
		self.assertAlmostEqual(DO.dose_factor("mb", "Gram", "BAG", item_factor=0.00004), 0.00004)
		self.assertAlmostEqual(
			DO.dose_factor("mb", "Gram", "Kilogram", item_factor=None, erpnext_factor=0.001), 0.001
		)
		self.assertAlmostEqual(DO.dose_factor("mb", "Gram", "Kilogram"), 0.001)
		self.assertIsNone(DO.dose_factor("mb", "Gram", "BAG"))

	def test_kg_total_leaves_doses_out(self):
		lines = [
			{"item_code": "silage", "qty": 15},
			{"item_code": "meal", "qty": 5},
			{"item_code": "diamond v", "qty": 7, "dose_uom": "Gram"},
			{"item_code": "meat grow", "qty": 60, "uom": "Millilitre"},
		]
		self.assertEqual(DO.kg_total(lines), 20)


class TestDoseLinesInARecipe(unittest.TestCase):
	def test_clean_keeps_a_dose_apart_from_kilos_of_the_same_item(self):
		out = TB._clean(
			[
				{"item_code": "yeast", "qty": 1},
				{"item_code": "yeast", "qty": 7, "dose_uom": "Gram"},
				{"item_code": "yeast", "qty": 2},
			]
		)
		self.assertEqual(out, [{"item_code": "yeast", "qty": 3.0}, {"item_code": "yeast", "qty": 7.0, "dose_uom": "Gram"}])

	def test_clean_keeps_a_lines_own_unit(self):
		out = TB._clean([{"item_code": "napier", "qty": 15, "uom": "Kilogram"}])
		self.assertEqual(out, [{"item_code": "napier", "qty": 15.0, "uom": "Kilogram"}])

	def test_seven_grams_is_not_seven_kilos(self):
		self.assertNotEqual(
			TB._signature([{"item_code": "yeast", "qty": 7}]),
			TB._signature([{"item_code": "yeast", "qty": 7, "dose_uom": "Gram"}]),
		)

	def test_a_kilogram_recipe_keeps_the_key_it_always_had(self):
		# Existing BOMs must still match themselves, with or without a unit read.
		self.assertEqual(
			TB._signature([{"item_code": "hay", "qty": 5}]),
			TB._signature([{"item_code": "hay", "qty": 5, "uom": "Kilogram"}]),
		)

	def test_three_litres_is_not_three_kilos(self):
		# A line's chosen unit is part of the recipe: changing kg to Litre must save a new revision.
		self.assertNotEqual(
			TB._signature([{"item_code": "molasses", "qty": 3, "uom": "Kg"}]),
			TB._signature([{"item_code": "molasses", "qty": 3, "uom": "Litre"}]),
		)
		self.assertEqual(
			TB._signature([{"item_code": "molasses", "qty": 3, "uom": "Kg"}]),
			TB._signature([{"item_code": "molasses", "qty": 3}]),
		)

	def test_row_units_for_a_dose(self):
		with patch.object(TB, "conversion_factor", return_value=0.001):
			self.assertEqual(
				TB.row_units("yeast", "Kilogram", {"item_code": "yeast", "qty": 7, "dose_uom": "Gram"}),
				("Gram", 0.001),
			)

	def test_row_units_borrows_the_replaced_rows_unit(self):
		old = frappe._dict(uom="Kilogram", conversion_factor=0.07)
		self.assertEqual(TB.row_units("hay", "BALE", {"item_code": "hay", "qty": 5}, old), ("Kilogram", 0.07))

	def test_row_units_converts_a_swapped_in_feed_weighed_in_kilos(self):
		with patch.object(TB, "conversion_factor", return_value=0.05):
			self.assertEqual(
				TB.row_units("napier", "BALE", {"item_code": "napier", "qty": 15, "uom": "Kilogram"}),
				("Kilogram", 0.05),
			)

	def test_a_unitless_line_replacing_a_dose_stays_that_dose(self):
		# The phone's manual feed sends {item_code, qty} only: 7 back for a 7 g row must stay 7 g, not 7 kg.
		old = frappe._dict(uom="Gram", conversion_factor=0.001)
		self.assertEqual(TB.row_units("yeast", "Kilogram", {"item_code": "yeast", "qty": 7}, old), ("Gram", 0.001))
		# Naming kilograms is a deliberate change of unit and is honoured.
		with patch.object(TB, "conversion_factor", return_value=1):
			self.assertEqual(
				TB.row_units("yeast", "Kilogram", {"item_code": "yeast", "qty": 0.007, "uom": "Kilogram"}, old),
				("Kilogram", 1),
			)

	def test_row_units_defaults_to_the_stock_unit(self):
		self.assertEqual(TB.row_units("bran", "Kilogram", {"item_code": "bran", "qty": 2}), ("Kilogram", 1))


class _Fake:
	def __init__(self, feeds=None, recipes=None):
		self.feeds, self.recipes = feeds or {}, recipes or {}

	def feed(self, item):
		return self.feeds.get(item)

	def recipe(self, item):
		return self.recipes.get(item)

	def name(self, item):
		return item.title()

	def rate(self, item):
		return None


def _rec(dm, cp=0):
	return {
		"dry_matter_pct": dm, "crude_protein_pct": cp, "carbohydrate_pct": 10,
		"fibre_ndf_pct": 0, "fat_pct": 0, "energy_me_mj_per_kg": 10,
		"calcium_pct": 0, "phosphorus_pct": 0, "category": "Forage", "nutrient_source": None,
	}


class TestNutritionDoesNotChokeOnDoses(unittest.TestCase):
	def setUp(self):
		self.src = _Fake(feeds={"silage": _rec(30, 8)})

	def test_a_dose_is_listed_not_weighed(self):
		got = FN.nutrition_of(
			[
				{"item_code": "silage", "qty": 10},
				{"item_code": "meat grow", "qty": 60, "dose_uom": "Millilitre"},
			],
			self.src,
		)
		self.assertEqual(got["as_fed_kg"], 10)
		self.assertEqual(got["missing"], [])
		self.assertEqual([(d["item_code"], d["qty"], d["uom"]) for d in got["doses"]], [("meat grow", 60, "Millilitre")])

	def test_a_bom_row_triple_in_grams_is_a_dose(self):
		got = FN.nutrition_of([("silage", 10, "Kilogram"), ("yeast", 7, "Gram")], self.src)
		self.assertEqual(got["as_fed_kg"], 10)
		self.assertEqual(len(got["doses"]), 1)


class TestExpandingKeepsDoses(unittest.TestCase):
	def setUp(self):
		# A 1000 kg shoat concentrate with 50 g of a premix in the batch.
		self.src = _Fake(recipes={"shoat meal": (1000.0, [("bran", 600.0), ("maize", 400.0)], "B", [("premix", 50.0, "Gram")])})

	def test_a_dose_in_the_ration_passes_through(self):
		out, expanded = EX.expand_lines(
			[{"item_code": "silage", "qty": 3}, {"item_code": "yeast", "qty": 7, "dose_uom": "Gram"}],
			source=self.src, concentrates=set(),
		)
		self.assertEqual(expanded, [])
		self.assertIn({"item_code": "yeast", "qty": 7.0, "dose_uom": "Gram"}, out)

	def test_a_dose_inside_a_concentrate_becomes_a_per_head_dose(self):
		out, expanded = EX.expand_lines(
			[{"item_code": "shoat meal", "qty": 2}], source=self.src, concentrates={"shoat meal"}
		)
		self.assertEqual(expanded, ["shoat meal"])
		by = {(r["item_code"], r.get("dose_uom")): r["qty"] for r in out}
		self.assertEqual(by[("bran", None)], 1.2)
		self.assertEqual(by[("premix", "Gram")], 0.1)


class TestSubstitutes(unittest.TestCase):
	FEEDS = {
		"maize silage": {"substitute_group": "Wet forage", "dry_matter_pct": 30, "feed_name": "Maize silage"},
		"napier": {"substitute_group": "wet forage ", "dry_matter_pct": 20, "feed_name": "Napier"},
		"sorghum": {"substitute_group": "Wet forage", "dry_matter_pct": 0, "feed_name": "Sorghum silage"},
		"old chop": {"substitute_group": "Wet forage", "dry_matter_pct": 25, "feed_name": "Old chop", "disabled": 1},
		"hay": {"substitute_group": "Dry forage", "dry_matter_pct": 90, "feed_name": "Hay"},
		"bran": {"substitute_group": None, "dry_matter_pct": 88, "feed_name": "Bran"},
	}

	def test_same_dry_matter(self):
		self.assertAlmostEqual(FS.dm_equivalent_kg(10, 30, 20), 15)

	def test_no_dry_matter_no_swap(self):
		self.assertIsNone(FS.dm_equivalent_kg(10, 30, 0))
		self.assertIsNone(FS.dm_equivalent_kg(10, None, 20))

	def test_only_the_same_group_is_offered(self):
		got = FS.substitutes_for("maize silage", self.FEEDS)
		self.assertEqual([s["item_code"] for s in got], ["napier", "sorghum"])

	def test_the_factor_is_kilos_per_kilo(self):
		napier = FS.substitutes_for("maize silage", self.FEEDS)[0]
		self.assertAlmostEqual(napier["factor"], 1.5)

	def test_a_feed_with_no_dry_matter_is_shown_but_not_swappable(self):
		sorghum = FS.substitutes_for("maize silage", self.FEEDS)[1]
		self.assertIsNone(sorghum["factor"])
		self.assertEqual(sorghum["reason"], "no dry matter recorded")

	def test_a_feed_with_no_group_has_no_substitutes(self):
		self.assertEqual(FS.substitutes_for("bran", self.FEEDS), [])
		self.assertEqual(FS.substitutes_for("unknown", self.FEEDS), [])


# ── On a site ────────────────────────────────────────────────────────────────


class TestTheFields(IntegrationTestCase):
	def test_feed_by_head_count_is_a_check_defaulting_to_on(self):
		df = frappe.get_meta("Livestock Settings").get_field("feed_by_head_count")
		self.assertEqual((df.fieldtype, str(df.default)), ("Check", "1"))

	def test_an_unset_feed_by_head_count_reads_as_on(self):
		frappe.db.sql("delete from `tabSingles` where doctype='Livestock Settings' and field='feed_by_head_count'")
		try:
			self.assertTrue(HC.feed_by_head_count_on())
		finally:
			frappe.db.rollback()

	def test_herds_carry_a_concentrate_mode(self):
		df = frappe.get_meta("Herds").get_field("concentrate_mode")
		self.assertEqual(df.fieldtype, "Select")
		self.assertEqual(df.options.split("\n"), list(CN.CONCENTRATE_MODES))
		self.assertEqual(df.default, CN.FARM_DEFAULT)

	def test_livestock_feed_carries_a_substitute_group(self):
		self.assertTrue(frappe.get_meta("Livestock Feed").get_field("substitute_group"))


class TestConcentrateModeOnASite(IntegrationTestCase):
	def setUp(self):
		self.herds = frappe.get_all("Herds", pluck="name", limit=2)
		if not self.herds:
			self.skipTest("needs a herd")

	def tearDown(self):
		frappe.db.rollback()

	def _farm(self, on):
		frappe.db.set_single_value("Livestock Settings", "premanufacture_concentrate", on)

	def _mode(self, herd, mode):
		frappe.db.set_value("Herds", herd, "concentrate_mode", mode, update_modified=False)

	def test_one_herd_on_pre_manufacture_keeps_the_concentrate_stage(self):
		self._farm(0)
		for h in frappe.get_all("Herds", pluck="name"):
			self._mode(h, CN.FARM_DEFAULT)
		self.assertFalse(CN.any_herd_premanufactures())
		self._mode(self.herds[0], CN.PRE_MANUFACTURE)
		self.assertTrue(CN.any_herd_premanufactures())
		CN.refuse_without_concentrate_stage()  # does not raise

	def test_a_herd_on_mix_from_raw_does_not_premanufacture_on_a_premanufacturing_farm(self):
		self._farm(1)
		self._mode(self.herds[0], CN.MIX_FROM_RAW)
		self.assertFalse(CN.herd_premanufactures(self.herds[0]))
		self.assertFalse(CN.premanufacture_by_herd()[self.herds[0]])

	def test_herd_rations_reports_it_per_herd(self):
		from upande_livestock.serverscripts.feeding.herd_rations import herd_rations

		self._farm(1)
		self._mode(self.herds[0], CN.MIX_FROM_RAW)
		got = herd_rations()
		row = next(r for r in got["herds"] if r["herd"] == self.herds[0])
		self.assertFalse(row["premanufacture"])
		self.assertIn("feed_by_head_count", got)


class TestManufactureAllWithTypedTotals(IntegrationTestCase):
	"""Feed by Head Count off: the operator's totals are what is mixed."""

	def setUp(self):
		from upande_livestock.serverscripts.common.calf_separation import fed_head_count

		self.herds = [
			h.name for h in frappe.get_all("Herds", fields=["name", "bom"], order_by="name asc")
			if h.bom and fed_head_count(h.name) > 0
		]
		if len(self.herds) < 2:
			self.skipTest("needs two herds with rations and animals")
		frappe.db.set_single_value("Livestock Settings", "feed_by_head_count", 0)

	def tearDown(self):
		frappe.db.rollback()

	def _go(self, **kw):
		calls = []

		def engine(herd, **k):
			calls.append((herd, k))
			return {"work_order": "WO-" + herd, "produced_qty": k.get("typed_total"), "issued_qty": 1, "uom": "Kilogram"}

		with patch("upande_livestock.serverscripts.feeding.feed_day_status._issues_on", return_value=[]), patch.object(
			MA, "guard_stock"
		), patch.object(MA, "_plan_concentrates", return_value=[]), patch.object(
			MA.feeding, "manufacture_herd_feed", engine
		):
			return MA.manufacture_all_feeds(**kw), calls

	def test_preview_offers_the_head_count_figure_as_a_suggestion(self):
		got, calls = self._go(preview=1)
		self.assertTrue(got["ok"], got)
		self.assertFalse(got["feed_by_head_count"])
		self.assertEqual(calls, [])
		for r in got["herds"]:
			self.assertEqual(r["qty"], r["suggested_qty"])

	def test_the_typed_total_is_what_is_mixed(self):
		got, calls = self._go(totals=frappe.as_json({self.herds[0]: 612.5}))
		self.assertTrue(got["ok"], got)
		self.assertEqual([c[0] for c in calls], [self.herds[0]])
		self.assertEqual(calls[0][1]["typed_total"], 612.5)

	def test_a_herd_left_blank_is_not_fed_a_number_nobody_saw(self):
		got, _calls = self._go(totals={self.herds[0]: 100})
		self.assertIn((self.herds[1], "no total entered"), [(s["herd"], s["reason"]) for s in got["skipped"]])

	def test_with_head_count_on_totals_are_ignored(self):
		frappe.db.set_single_value("Livestock Settings", "feed_by_head_count", 1)
		got, calls = self._go(totals={self.herds[0]: 1})
		self.assertTrue(got["feed_by_head_count"])
		self.assertNotIn("typed_total", calls[0][1])


class TestManufactureFeedTypedTotal(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _call(self, on):
		from upande_livestock.serverscripts.feeding import manufacture_feed as MF

		frappe.db.set_single_value("Livestock Settings", "feed_by_head_count", 1 if on else 0)
		with patch.object(MF, "guard_stock"), patch.object(
			MF.feeding, "manufacture_herd_feed", return_value={"work_order": "WO"}
		) as engine:
			MF.manufacture_feed("any herd", total_qty=500)
		return engine.call_args.kwargs["typed_total"]

	def test_off_the_total_reaches_the_engine(self):
		self.assertEqual(self._call(on=False), 500)

	def test_on_it_does_not(self):
		self.assertIsNone(self._call(on=True))
