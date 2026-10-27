# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which animals the figures put forward, and why each one is there.

The suggestion list is the one part of culling that nobody signs: it only
decides what a manager reads first. So an animal gaining on target with a clean
health record is never on it, and one who is carries the gain and health facts
that put it there. Nothing here is about milk.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.culling.cull_candidates import cull_candidates
from upande_livestock.serverscripts.culling.cull_evidence import cull_evidence
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, submit_weight


def _find(got, animal):
	for row in got["candidates"]:
		if row["animal"] == animal:
			return row
	return None


def _reasons(row):
	return {r["key"] for r in (row or {}).get("reasons", [])}


def _gainer(herd, start_kg, end_kg, days=60):
	animal = make_animal(herd)
	submit_weight(animal.name, start_kg, days_ago=days)
	submit_weight(animal.name, end_kg, days_ago=0)
	return animal


class CullTestCase(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.herd = make_herd("ZZ Cull Herd", "Fattening", min_kg=0, max_kg=900, target_adg_kg=1.0).name


class TestOnlyAnimalsWithSomethingAgainstThemAreSuggested(CullTestCase):
	def test_an_animal_gaining_on_target_is_not_on_the_list(self):
		good = _gainer(self.herd, 200, 270)  # 1.17 kg/day
		got = cull_candidates()
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertIsNone(_find(got, good.name))

	def test_an_animal_with_no_weighings_is_not_on_the_list(self):
		bare = make_animal(self.herd)
		self.assertIsNone(_find(cull_candidates(), bare.name))

	def test_the_whole_herd_is_still_counted(self):
		_gainer(self.herd, 200, 270)
		got = cull_candidates()
		self.assertGreaterEqual(got["considered"], got["flagged_count"])


class TestPoorGainPutsAnimalForward(CullTestCase):
	def test_poor_gainer_is_candidate(self):
		slow = _gainer(self.herd, 200, 218)  # 0.3 kg/day against a target of 1.0
		row = _find(cull_candidates(), slow.name)
		self.assertIsNotNone(row, "an animal gaining 0.3 against 1.0 is not on the list")
		self.assertIn("poor_gain", _reasons(row))
		self.assertEqual(row["period_adg"], 0.3)
		self.assertEqual(row["target_adg"], 1.0)

	def test_the_reason_says_the_gain_and_the_target(self):
		slow = _gainer(self.herd, 200, 218)
		reason = next(r for r in _find(cull_candidates(), slow.name)["reasons"] if r["key"] == "poor_gain")
		self.assertIn("0.30", reason["label"])
		self.assertIn("1.00", reason["label"])

	def test_a_herd_with_no_target_puts_nobody_forward_on_gain(self):
		herd = make_herd("ZZ Cull Untargeted").name
		frappe.db.set_single_value("Livestock Settings", "custom_target_growth_gday", 0)
		slow = _gainer(herd, 200, 218)
		self.assertIsNone(_find(cull_candidates(), slow.name))

	def test_a_weight_loser_outranks_a_slow_gainer(self):
		losing = _gainer(self.herd, 250, 220)
		slow = _gainer(self.herd, 200, 230)  # 0.5
		got = cull_candidates()
		self.assertGreater(_find(got, losing.name)["score"], _find(got, slow.name)["score"])

	def test_the_score_is_the_sum_of_the_reasons(self):
		slow = _gainer(self.herd, 200, 218)
		row = _find(cull_candidates(), slow.name)
		self.assertEqual(row["score"], sum(r["weight"] for r in row["reasons"]))

	def test_no_milk_evidence(self):
		slow = _gainer(self.herd, 200, 218)
		got = cull_candidates()
		row = _find(got, slow.name)
		text = repr(row).lower() + repr(got["herd"]).lower()
		for word in ("milk", "calving", "abortion", "lactation", "service"):
			self.assertNotIn(word, text)
		evidence = cull_evidence(animal=slow.name)
		self.assertTrue(evidence.get("ok"), evidence.get("error"))
		self.assertNotIn("was_productive", evidence)
		self.assertNotIn("milk", repr(evidence).lower())

	def test_the_evidence_sentence_names_the_gain(self):
		slow = _gainer(self.herd, 200, 218)
		evidence = cull_evidence(animal=slow.name)
		self.assertIn("0.30", evidence["case"])
		self.assertEqual(evidence["below"], 1)


class TestDaysUnderTreatmentPutAnimalForward(CullTestCase):
	def setUp(self):
		super().setUp()
		self.animal = _gainer(self.herd, 200, 270)  # gaining well; only health argues

	def _case(self, opened_back):
		frappe.get_doc({
			"doctype": "Livestock Health Case", "animal": self.animal.name,
			"opened_date": add_days(today(), -opened_back), "case_status": "Open",
			"presenting_symptoms": "Off his feed",
		}).insert(ignore_permissions=True).submit()

	def test_a_long_illness_is_a_reason(self):
		self._case(60)
		row = _find(cull_candidates(), self.animal.name)
		self.assertIsNotNone(row, "sixty days under treatment did not put him forward")
		self.assertIn("sick", _reasons(row))
		self.assertNotIn("poor_gain", _reasons(row))

	def test_an_open_case_counts_its_days_to_today(self):
		self._case(60)
		reason = next(r for r in _find(cull_candidates(), self.animal.name)["reasons"] if r["key"] == "sick")
		self.assertIn("60", reason["label"])

	def test_a_short_illness_is_not_a_reason_on_its_own(self):
		self._case(3)
		self.assertIsNone(_find(cull_candidates(), self.animal.name))

	def test_the_years_carry_the_days_ill(self):
		self._case(60)
		row = _find(cull_candidates(), self.animal.name)
		self.assertGreater(sum(y["sick_days"] for y in row["years"]), 0)

	def test_the_evidence_includes_the_health_history(self):
		self._case(60)
		evidence = cull_evidence(animal=self.animal.name)
		self.assertEqual(evidence["health_cases"], 1)
		self.assertIn("60 days ill", evidence["case"])
