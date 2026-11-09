"""The nutrition maths: pure, tested without a database.

Run:
    cd sites && ../env/bin/python -m unittest \
        upande_livestock.serverscripts.tests.test_feed_nutrition
"""

import unittest

from upande_livestock.serverscripts.feeding import feed_nutrition as FN


def rec(dm, cp=0, carb=0, ndf=0, fat=0, me=0, category="Energy (grain / by-product)", source=None):
	return {
		"dry_matter_pct": dm, "crude_protein_pct": cp, "carbohydrate_pct": carb,
		"fibre_ndf_pct": ndf, "fat_pct": fat, "energy_me_mj_per_kg": me,
		"calcium_pct": 0, "phosphorus_pct": 0, "category": category, "nutrient_source": source,
	}


class Fake:
	def __init__(self, feeds=None, recipes=None, rates=None):
		self.feeds, self.recipes, self.rates = feeds or {}, recipes or {}, rates or {}

	def feed(self, item):
		return self.feeds.get(item)

	def recipe(self, item):
		return self.recipes.get(item)

	def name(self, item):
		return item.title()

	def rate(self, item):
		return self.rates.get(item)


# bran: 90% DM, CP 16; silage: 30% DM, CP 8.  1 kg bran + 3 kg silage as fed.
BASE = Fake(
	feeds={
		"bran": rec(90, cp=16, carb=40, ndf=40, fat=4, me=11),
		"silage": rec(30, cp=8, carb=20, ndf=55, fat=3, me=9),
		"salt": rec(99, category="Mineral & vitamin"),
	},
	rates={"bran": 40.0, "silage": 5.0, "salt": 20.0},
)


class TestWeightedOnDryMatter(unittest.TestCase):
	def test_totals_and_dm_weighting(self):
		out = FN.nutrition_of([("bran", 1), ("silage", 3)], BASE)
		self.assertAlmostEqual(out["as_fed_kg"], 4)
		# DM: 0.9 + 0.9 = 1.8 kg
		self.assertAlmostEqual(out["dm_kg"], 1.8)
		# CP: (0.9*16 + 0.9*8) / 1.8 = 12 — NOT the as-fed weighting (1*16+3*8)/4 = 10
		self.assertAlmostEqual(out["cp_pct"], 12.0)
		self.assertAlmostEqual(out["me_mj_per_kg"], 10.0)
		self.assertAlmostEqual(out["dm_pct"], 45.0)

	def test_cost(self):
		out = FN.nutrition_of([("bran", 1), ("silage", 3)], BASE)
		self.assertAlmostEqual(out["cost"], 40 + 15)
		self.assertEqual(out["unpriced"], [])

	def test_empty(self):
		out = FN.nutrition_of([], BASE)
		self.assertEqual(out["dm_kg"], 0)
		self.assertEqual(out["cp_pct"], 0)

	def test_accepts_dict_lines_and_drops_zero(self):
		out = FN.nutrition_of([{"item_code": "bran", "qty": 2}, {"item_code": "silage", "qty": 0}], BASE)
		self.assertAlmostEqual(out["as_fed_kg"], 2)


class TestMadeFeedsAreExpanded(unittest.TestCase):
	def setUp(self):
		# 10 kg of "meal" = 4 bran + 6 silage; a typed record on it that LIES.
		self.src = Fake(
			feeds={**BASE.feeds, "meal": rec(90, cp=99, source="Lab analysis", category="Concentrate (made)")},
			recipes={"meal": (10.0, [("bran", 4.0), ("silage", 6.0)], "BOM-meal")},
			rates=BASE.rates,
		)

	def test_made_feed_uses_its_recipe_not_its_record(self):
		out = FN.nutrition_of([("meal", 5)], self.src)
		# 5 kg meal = 2 bran + 3 silage -> DM 1.8+0.9 = 2.7 ; CP (1.8*16+0.9*8)/2.7 = 13.33
		self.assertAlmostEqual(out["as_fed_kg"], 5)
		self.assertAlmostEqual(out["dm_kg"], 2.7)
		self.assertAlmostEqual(out["cp_pct"], 13.333, places=2)
		self.assertAlmostEqual(out["cost"], 2 * 40 + 3 * 5)

	def test_lab_check_is_shown_beside_the_computed_figure(self):
		line = FN.nutrition_of([("meal", 5)], self.src)["lines"][0]
		self.assertTrue(line["made"])
		self.assertEqual(line["lab_check"]["cp_pct"], 99)
		self.assertAlmostEqual(line["computed"]["cp_pct"], 13.333, places=2)

	def test_nested_made_feeds_expand_recursively(self):
		src = Fake(
			feeds=BASE.feeds,
			recipes={
				"tmr": (4.0, [("meal", 2.0), ("silage", 2.0)], "B1"),
				"meal": (10.0, [("bran", 5.0), ("silage", 5.0)], "B2"),
			},
		)
		out = FN.nutrition_of([("tmr", 4)], src)
		# tmr 4 kg = 2 meal (1 bran + 1 silage) + 2 silage = 1 bran + 3 silage
		ref = FN.nutrition_of([("bran", 1), ("silage", 3)], BASE)
		self.assertAlmostEqual(out["cp_pct"], ref["cp_pct"])
		self.assertAlmostEqual(out["dm_kg"], ref["dm_kg"])

	def test_a_recipe_that_loops_does_not_hang(self):
		src = Fake(feeds=BASE.feeds, recipes={"a": (2.0, [("b", 1.0), ("bran", 1.0)], "x"),
		                                      "b": (1.0, [("a", 1.0)], "y")})
		out = FN.nutrition_of([("a", 2)], src)
		self.assertAlmostEqual(out["as_fed_kg"], 2)


class TestMissingData(unittest.TestCase):
	def test_unknown_item_is_listed_and_counts_as_zero(self):
		out = FN.nutrition_of([("bran", 1), ("mystery", 5)], BASE)
		self.assertEqual([m["item_code"] for m in out["missing"]], ["mystery"])
		self.assertEqual(out["missing"][0]["qty_kg"], 5)
		# as fed counts it, DM and nutrients do not
		self.assertAlmostEqual(out["as_fed_kg"], 6)
		self.assertAlmostEqual(out["dm_kg"], 0.9)
		self.assertAlmostEqual(out["cp_pct"], 16.0)
		self.assertEqual([u["item_code"] for u in out["unpriced"]], ["mystery"])

	def test_missing_inside_a_made_feed_is_named(self):
		src = Fake(feeds={"bran": BASE.feeds["bran"]}, recipes={"meal": (2.0, [("bran", 1.0), ("ghost", 1.0)], "b")})
		out = FN.nutrition_of([("meal", 2)], src)
		self.assertEqual(out["missing"][0]["item_code"], "ghost")
		self.assertEqual(out["missing"][0]["via"], "meal")

	def test_a_mineral_with_zero_protein_is_not_missing(self):
		out = FN.nutrition_of([("salt", 0.1)], BASE)
		self.assertEqual(out["missing"], [])

	def test_a_record_with_no_figures_is_incomplete(self):
		src = Fake(feeds={"x": rec(88)})
		out = FN.nutrition_of([("x", 1)], src)
		self.assertEqual(out["missing"][0]["reason"], "incomplete record")
		self.assertIn("crude_protein_pct", out["missing"][0]["fields"])

	def test_each_item_is_listed_once(self):
		out = FN.nutrition_of([("ghost", 1), ("ghost", 2)], BASE)
		self.assertEqual(len(out["missing"]), 1)
		self.assertEqual(out["missing"][0]["qty_kg"], 3)


if __name__ == "__main__":
	unittest.main()
