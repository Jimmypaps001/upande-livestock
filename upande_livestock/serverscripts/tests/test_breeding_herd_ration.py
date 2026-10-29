# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Breeding bulls eat with the breeding herd they live in; calves with their mothers do not."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common.animal import live_herd_count, recompute_herd_count
from upande_livestock.serverscripts.common.calf_separation import fed_head_count, head_breakdown
from upande_livestock.serverscripts.feeding._engine import _herd_bom
from upande_livestock.serverscripts.feeding.herd_rations import herd_rations
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd


def ago(days):
	return add_days(today(), -days)


class TestBreedingHerdRation(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_active": 1}, "name")
		self.herd = make_herd("ZZ BR Group", "Breeding", bom=self.bom).name if self.bom else make_herd(
			"ZZ BR Group", "Breeding").name
		for _ in range(3):
			make_animal(self.herd, sex="Female", date_of_birth=ago(3000))
		self.bull = make_animal(self.herd, sex="Male", date_of_birth=ago(2500))
		self.calf = make_animal(self.herd, sex="Male", date_of_birth=ago(60))
		recompute_herd_count(self.herd)

	def test_the_bull_counts_in_the_herd_head(self):
		self.assertEqual(live_herd_count(self.herd), 5)
		self.assertEqual(frappe.db.get_value("Herds", self.herd, "number_of_animals"), 5)

	def test_breakdown_is_females_bulls_and_calves(self):
		got = head_breakdown(self.herd)
		self.assertEqual((got["females"], got["bulls"], got["calves"], got["fed"]), (3, 1, 1, 4))

	def test_the_ration_is_made_for_cows_and_bulls_not_for_the_calf(self):
		self.assertEqual(fed_head_count(self.herd), 4)

	def test_the_herd_ration_screen_says_how_many_of_each(self):
		if not self.bom:
			self.skipTest("no BOM on this site")
		rows = {r["herd"]: r for r in herd_rations()["herds"]}
		row = rows[self.herd]
		self.assertEqual((row["heads"], row["fed_heads"], row["bulls"], row["females"], row["calves"]),
		                 (5, 4, 1, 3, 1))
		self.assertEqual(row["day_kg"], row["per_head_kg"] * 4)

	def test_the_engine_feeds_those_heads(self):
		if not self.bom:
			self.skipTest("no BOM on this site")
		_herd_doc, _bom, heads = _herd_bom(self.herd)
		self.assertEqual(heads, 4)
