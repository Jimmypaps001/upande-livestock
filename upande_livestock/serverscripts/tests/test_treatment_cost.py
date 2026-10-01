"""What a treatment cost, and what the case has cost so far.

`Livestock Health Treatment.cost` exists and nothing ever wrote it.
`Livestock Health Case.total_treatment_cost` is read_only and nothing ever
assigned it. Two halves of one unfinished feature — which is why the Health
page reads "TREATMENT COST — written down on 0 of 25 cases" and always would.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import health_case as HC
from upande_livestock.upande_livestock.doctype.livestock_health_case import (
	livestock_health_case as LHC,
)


class Row(dict):
	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError as e:
			raise AttributeError(k) from e

	def __setattr__(self, k, v):
		self[k] = v


class Case:
	def __init__(self, treatments):
		self.treatments = treatments
		self.total_treatment_cost = None


class TestWhatOneTreatmentCost(unittest.TestCase):
	def test_it_is_priced_at_the_store_it_came_from(self):
		with patch.object(HC.frappe.db, "get_value", return_value=250.0):
			row = HC.treatment_row(
				{"drug_item": "DRUG-A", "qty": 4,
				 "source_warehouse": "Drug/ Medicine store- old office - KR"}
			)
		self.assertEqual(row["cost"], 1000.0)

	def test_a_cost_the_caller_typed_wins(self):
		"""An invoice beats a valuation. The farm's number is not overwritten."""
		with patch.object(HC.frappe.db, "get_value", return_value=250.0):
			row = HC.treatment_row(
				{"drug_item": "DRUG-A", "qty": 4, "cost": 900,
				 "source_warehouse": "Drug/ Medicine store- old office - KR"}
			)
		self.assertEqual(row["cost"], 900.0)

	def test_a_named_store_with_no_bin_row_costs_nothing(self):
		"""The store was named and does not hold it — so there is no rate HERE.

		This used to fall back to `Item.valuation_rate`, the item master's
		static figure, which is unrelated to any warehouse and often stale by an
		order of magnitude. Pricing the treatment at it would contradict this
		module's own reason for taking the store into account, and would do so
		in exactly the case the whole branch exists for: a named store with no
		Bin row. Found by the whole-branch review.
		"""
		seen = {}

		def fake_get_value(doctype, *a, **kw):
			seen.setdefault("doctypes", []).append(doctype)
			return None

		with patch.object(HC.frappe.db, "get_value", side_effect=fake_get_value):
			row = HC.treatment_row(
				{"drug_item": "DRUG-A", "qty": 4,
				 "source_warehouse": "Drug/ Medicine store- old office - KR"}
			)
		self.assertEqual(row["cost"], 0.0)
		# `treatment_row` also asks for an Employee (administered_by), so this
		# checks what it must NOT ask for rather than the whole call list.
		self.assertIn("Bin", seen["doctypes"])
		self.assertNotIn(
			"Item", seen["doctypes"],
			"a named store that holds none of it must not be priced off the Item master",
		)

	def test_a_row_with_no_store_at_all_costs_nothing(self):
		row = HC.treatment_row({"drug_item": "DRUG-A", "qty": 4})
		self.assertEqual(row["cost"], 0.0)

	def test_a_free_text_drug_is_not_priced(self):
		"""No item, no stock, no valuation to look up."""
		row = HC.treatment_row({"drug_name_text": "Something from the vet's bag", "qty": 1})
		self.assertEqual(row["cost"], 0.0)


class TestWhatTheCaseHasCost(unittest.TestCase):
	def test_the_case_sums_its_treatments(self):
		case = Case([Row(cost=1000.0), Row(cost=250.0)])
		LHC.LivestockHealthCase.recompute_treatment_cost(case)
		self.assertEqual(case.total_treatment_cost, 1250.0)

	def test_removing_the_last_treatment_takes_the_total_back_to_zero(self):
		case = Case([])
		case.total_treatment_cost = 1250.0
		LHC.LivestockHealthCase.recompute_treatment_cost(case)
		self.assertEqual(case.total_treatment_cost, 0.0)


class TestTheTotalSurvivesTheRealPath(unittest.TestCase):
	"""The roll-up has to run where treatments are actually added.

	Found by the whole-branch review, and it is the whole feature: treatments
	are `allow_on_submit` rows appended to an already-submitted case, so both
	`treat_animal` and `add_case_treatment` reach `Document.save()` with
	`_action == "update_after_submit"`. Frappe runs `before_update_after_submit`
	on that path and NOT `validate` — so a roll-up hung off `validate` fires
	exactly twice per case, at insert and at submit, both times with no
	treatments on it. `total_treatment_cost` was written as 0.0 and never again,
	which is the same "0 of 25 cases" the tile already showed.
	"""

	DRUG = "LSK-AB-OTC"

	def test_a_treatment_added_to_a_submitted_case_updates_the_total(self):
		from upande_livestock.serverscripts.health.treat_animal import treat_animal

		animal = frappe.db.get_value("Animal", {"status": "Active"}, "name")
		res = treat_animal({
			"animal": animal,
			"open_new": 1,
			"presenting_symptoms": "Warm, off her feed",
			"operator": "10212",
			"treatments": [{"drug_item": self.DRUG, "qty": 3, "cost": 120}],
		})
		self.assertTrue(res.get("ok"), res.get("error"))
		self.addCleanup(frappe.db.rollback)

		stored = frappe.db.get_value(
			"Livestock Health Case", res["case"], "total_treatment_cost"
		)
		self.assertEqual(
			flt(stored), 120.0,
			"the case still reports 0 — the roll-up never ran where treatments are added",
		)


from frappe.utils import flt  # noqa: E402  (used by the real-path test above)
