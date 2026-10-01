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

	def test_a_drug_with_no_bin_row_costs_nothing_rather_than_failing(self):
		with patch.object(HC.frappe.db, "get_value", return_value=None):
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
