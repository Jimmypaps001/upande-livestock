# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Mutara demo seed: head counts, herd totals, the planted cases, and a re-run that changes nothing.

Reads the seeded site; skips when the seed has not been run. The re-run test runs
the seed again (about ten seconds when there is nothing to do) and compares counts.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.demo import seed_mutara_beef as seed
from upande_livestock.serverscripts.common import kinship, sire_inference
from upande_livestock.serverscripts.common.calf_separation import separation_due


def _seeded():
	return frappe.db.exists("Animal", {"origin": "Born on Farm"}) and frappe.db.exists("Herds", seed.LG1)


class TestSeedMutaraBeef(IntegrationTestCase):
	def setUp(self):
		if not _seeded():
			raise unittest.SkipTest("run upande_livestock.demo.seed_mutara_beef.execute first")
		self.plan = seed.build_plan()
		self.planted = self.plan.planted

	def test_500_animals_207_females_293_males(self):
		counts = seed.counts()
		self.assertEqual((counts["Female"], counts["Male"], sum(counts.values())), (207, 293, 500))
		self.assertEqual(len(self.plan.animals), 500)

	def test_herd_totals(self):
		def heads(herd, sex):
			return frappe.db.count("Animal", {"current_herd": herd, "sex": sex, "status": "Active"})

		self.assertEqual((heads(seed.WEANERS, "Female"), heads(seed.WEANERS, "Male")), (37, 0))
		self.assertEqual((heads(seed.BH, "Female"), heads(seed.BH, "Male")), (50, 2))
		self.assertEqual(heads(seed.RESERVE, "Male"), 4)
		self.assertEqual([heads(seed.STARTERS, "Male"), heads(seed.GROWERS, "Male"), heads(seed.FINISHERS, "Male")],
		                 [90, 70, 90])
		# calves live in their mother's herd, and there is no Calves herd
		self.assertFalse(frappe.db.exists("Herds", "Calves"))
		calves = frappe.get_all("Animal", filters={"origin": "Born on Farm", "current_herd": ["in", [seed.LG1, seed.LG2]],
		                                         "repro_status": "Calf"}, fields=["sex", "dam", "current_herd"])
		self.assertEqual((len(calves), sum(1 for c in calves if c.sex == "Female")), (63, 30))
		self.assertTrue(all(frappe.db.get_value("Animal", c.dam, "current_herd") == c.current_herd for c in calves))
		# two bulls with each mating group; cows 50 + 40
		for herd, bulls in ((seed.BH, 2), (seed.LG1, 2), (seed.LG2, 2)):
			self.assertEqual(frappe.db.count("Animal", {"current_herd": herd, "sex": "Male", "repro_status": "Bull"}), bulls)

	def test_a_dozen_calves_are_due_to_leave(self):
		self.assertEqual(len([c for c in separation_due() if c["animal"] in self.planted["dozen_past_210"]]), 12)

	def test_band_edge_cases(self):
		w = self.planted["weights"]
		for tag in w["starters_over_band"] + w["growers_over_band"]:
			self.assertTrue(frappe.db.exists("Livestock Alert", {"animal": tag, "alert_kind": "Weight Band Move Due",
			                                                    "status": "Open"}), tag)
		self.assertEqual(frappe.db.get_value("Animal", w["grower_exactly_250"], "last_weight_kg"), 250.0)
		self.assertEqual(frappe.db.get_value("Animal", w["finisher_exactly_280"], "last_weight_kg"), 280.0)
		for tag in (w["grower_exactly_250"], w["finisher_exactly_280"]):
			self.assertFalse(frappe.db.exists("Livestock Alert", {"animal": tag, "alert_kind": "Weight Band Move Due",
			                                                     "status": "Open"}))
		self.assertTrue(all(frappe.db.get_value("Animal", t, "last_weight_kg") >= 450 for t in w["exit_ready"]))

	def test_cow_with_calf_has_her_service_and_the_calf_has_the_inferred_sire(self):
		chain = self.plan.chains[0]
		calf = frappe.db.get_value("Animal", chain["calf"], ["dam", "sire"], as_dict=True)
		self.assertEqual(calf.dam, chain["cow"])
		self.assertTrue(calf.sire)
		self.assertTrue(frappe.db.exists("Livestock Event", {"animal": chain["cow"], "event_type": "Service",
		                                                    "service_type": "Natural", "sire_inferred": 1}))

	def test_planted_sire_daughter(self):
		case = self.planted["sire_daughter"]
		found = {c["other"] for c in kinship.conflicts(case["bull"], seed.BH) if c["relation"] == "sire-daughter"}
		self.assertEqual(found, set(case["heifers"]))
		for tag in case["heifers"]:
			self.assertTrue(frappe.db.exists("Livestock Alert", {"animal": tag, "alert_kind": "Inbreeding Risk",
			                                                    "status": "Open"}))

	def test_planted_dam_son(self):
		case = self.planted["dam_son"]
		got = kinship.conflicts(case["bull"], case["herd"])
		self.assertIn(("dam-son", case["dam"]), [(c["relation"], c["shared_parent"]) for c in got])

	def test_planted_half_and_full_siblings(self):
		bull = self.planted["half_siblings"]["bull"]
		got = {(c["other"], c["relation"], c["shared_parent"]) for c in kinship.conflicts(bull, seed.BH)}
		for heifer in self.planted["half_siblings"]["heifers"]:
			self.assertIn((heifer, "half-siblings", self.planted["half_siblings"]["shared_sire"]), got)
		full = self.planted["full_siblings"]
		self.assertIn((full["heifer"], "full-siblings", full["dam"]), got)

	def test_planted_two_candidate_sires(self):
		case = self.planted["two_candidates"]
		for cow in case["cows"]:
			service = frappe.db.get_value("Livestock Event", {"animal": cow, "event_type": "Service"},
			                              ["service_date", "sire_animal"], as_dict=True)
			self.assertFalse(service.sire_animal)
			found = sire_inference.candidate_sires(cow, service.service_date)
			self.assertEqual(sorted(c["animal"] for c in found), sorted(case["bulls"]))

	def test_selection_notes_are_on_the_young_bulls(self):
		rows = frappe.get_all("Animal", filters={"stream": "Breeding", "breeding_note": ["is", "set"]},
		                      fields=["breeding_note", "breeding_note_by"])
		self.assertEqual(len(rows), 2)
		self.assertTrue(all(len(r.breeding_note) >= 20 and r.breeding_note_by for r in rows))

	def test_the_simulated_user_is_ready(self):
		user = frappe.get_doc("User", seed.SIM_USER)
		roles = {r.role for r in user.roles}
		self.assertTrue({"Livestock Attendant", "Livestock Breeder", "Livestock Manager"} <= roles)
		self.assertNotIn("System Manager", roles)
		self.assertTrue(frappe.db.exists("Employee", {"user_id": seed.SIM_USER}))

	def test_every_herd_has_a_ration_and_the_breeding_herds_feed_their_bulls(self):
		from upande_livestock.serverscripts.common.calf_separation import fed_head_count

		for herd, *_ in seed.HERDS:
			self.assertTrue(frappe.db.get_value("Herds", herd, "bom"), herd)
		from upande_livestock.serverscripts.common.calf_separation import head_breakdown

		heads = frappe.db.get_value("Herds", seed.LG1, "number_of_animals")
		calves = head_breakdown(seed.LG1)["calves"]
		self.assertGreater(calves, 0)
		self.assertEqual(fed_head_count(seed.LG1), heads - calves)

	def test_rerun_changes_nothing(self):
		tables = ("Animal", "Livestock Event", "Livestock Weight Record", "Livestock Alert", "Herds", "Stock Entry")
		before = {t: frappe.db.count(t) for t in tables}
		seed.execute(skip_stock=True)
		self.assertEqual({t: frappe.db.count(t) for t in tables}, before)
