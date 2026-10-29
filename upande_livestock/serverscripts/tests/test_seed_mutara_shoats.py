# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Mutara shoats seed: four herds, their ledgers, samples, treatments, and a re-run that changes nothing.

Reads the seeded site; skips when the seed has not been run.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.demo import seed_mutara_shoats as seed
from upande_livestock.serverscripts.common import shoats


def _seeded():
	return all(frappe.db.exists("Herds", h) for h in seed.HERDS) and \
		frappe.db.exists("Herd Count Event", {"herd": "Dorper Flock", "docstatus": 1})


class TestSeedMutaraShoats(IntegrationTestCase):
	def setUp(self):
		if not _seeded():
			raise unittest.SkipTest("run upande_livestock.demo.seed_mutara_shoats.execute first")
		self.plan = seed.build_plan()

	def test_two_sheep_flocks_and_two_goat_herds_by_number(self):
		got = {h.name: h for h in frappe.get_all("Herds", filters={"name": ["in", list(seed.HERDS)]},
		                                        fields=["name", "counting", "species", "breed", "paddock", "bom"])}
		self.assertEqual({n: (h.species, h.breed) for n, h in got.items()},
		                 {"Dorper Flock": ("Sheep", "Dorper"), "Red Maasai Flock": ("Sheep", "Red Maasai"),
		                  "Galla Goat Herd": ("Goat", "Galla"), "Boer Goat Herd": ("Goat", "Boer")})
		for h in got.values():
			self.assertEqual(h.counting, "By number")
			self.assertTrue(h.paddock and h.bom)
		self.assertEqual(frappe.db.count("Animal", {"current_herd": ["in", list(seed.HERDS)]}), 0)

	def test_heads_are_realistic_and_match_the_plan(self):
		for name, p in self.plan.items():
			head = shoats.head(name)
			self.assertEqual({k: head[k] for k in shoats.CLASSES}, p["final"], name)
			self.assertTrue(60 <= head["total"] <= 150, (name, head["total"]))
			self.assertEqual(frappe.db.get_value("Herds", name, "number_of_animals"), head["total"])

	def test_each_herd_has_a_years_ledger(self):
		for name in seed.HERDS:
			kinds = {r.event_type: r.n for r in frappe.db.sql(
				"""SELECT event_type, COUNT(*) n FROM `tabHerd Count Event` WHERE herd=%s AND docstatus=1
				   GROUP BY event_type""", (name,), as_dict=True)}
			for kind in ("Purchase", "Birth", "Death", "Sale", "Weaning", "Head Count"):
				self.assertGreaterEqual(kinds.get(kind, 0), 1, (name, kind, kinds))
			self.assertEqual(kinds["Mating"], 3)
			first = frappe.db.sql("SELECT MIN(event_date) FROM `tabHerd Count Event` WHERE herd=%s", (name,))[0][0]
			self.assertGreaterEqual((seed.ANCHOR - first).days, 360)

	def test_two_seasons_delivered_and_one_pending(self):
		for name in seed.HERDS:
			status = [m["status"] for m in shoats.matings(name)]
			self.assertEqual(sorted(status), ["Delivered", "Delivered", "Pending"], name)

	def test_head_counts_carry_a_planted_variance(self):
		slips = frappe.db.sql("""SELECT COUNT(*) FROM `tabHerd Count Event` WHERE event_type='Head Count' AND docstatus=1
		                         AND herd IN %s AND variance_females != 0""", (tuple(seed.HERDS),))[0][0]
		self.assertGreaterEqual(slips, 4)

	def test_monthly_weight_samples_and_a_live_weight(self):
		for name in seed.HERDS:
			n = frappe.db.count("Herd Weight Sample", {"herd": name, "sample_class": "All"})
			self.assertGreaterEqual(n, 12)
			self.assertGreater(shoats.live_weight(name)["live_weight_kg"], 0)

	def test_treatments_issued_from_the_drug_store_one_still_in_withdrawal(self):
		for name in seed.HERDS:
			rows = frappe.get_all("Herd Treatment", filters={"herd": name, "docstatus": 1},
			                      fields=["stock_entry", "treatment_type", "warehouse"])
			self.assertEqual(len(rows), 5)
			self.assertEqual({r.treatment_type for r in rows}, set(shoats.TREATMENT_TYPES))
			self.assertTrue(all(r.stock_entry and r.warehouse == "Drug Store - MUT" for r in rows))
			self.assertTrue(shoats.herd_row(name)["in_withdrawal"])

	def test_a_second_run_changes_nothing(self):
		def snapshot():
			return (shoats.shoat_herd_numbers(),
			        frappe.db.count("Herd Count Event"), frappe.db.count("Herd Weight Sample"),
			        frappe.db.count("Herd Treatment"), frappe.db.count("Stock Entry"), frappe.db.count("BOM"))

		before = snapshot()
		seed.execute()
		self.assertEqual(snapshot(), before)
