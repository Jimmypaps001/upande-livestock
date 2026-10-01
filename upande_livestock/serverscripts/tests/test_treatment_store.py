"""A treatment says which store the drug came out of, and which batch.

`Livestock Drug Issue` has carried `source_warehouse` and `batch_no` all along;
`Livestock Health Treatment` carried neither, so every treatment on the live
site issued from `drug_warehouse()` — `Livestock Drug Store - KR`, a warehouse
with zero stocked bins. The picker offers 46 drugs and the issue then asks a
shelf holding none of them.
"""

import unittest

import frappe

from upande_livestock.serverscripts.common.health_case import treatment_row


class TestTheTreatmentRowCarriesItsStore(unittest.TestCase):
	def test_the_doctype_has_the_two_columns(self):
		meta = frappe.get_meta("Livestock Health Treatment")
		store = meta.get_field("source_warehouse")
		self.assertTrue(store, "a treatment has nowhere to say where the drug came from")
		self.assertEqual(store.fieldtype, "Link")
		self.assertEqual(store.options, "Warehouse")
		self.assertTrue(meta.get_field("batch_no"), "a treatment cannot name a batch")

	def test_treatment_row_passes_the_store_through(self):
		row = treatment_row(
			{"drug_item": "LSK-SEMEN-TEST", "qty": 2,
			 "source_warehouse": "Drug/ Medicine store- old office - KR",
			 "batch_no": "DAIR-2026-00277"}
		)
		self.assertEqual(row["source_warehouse"], "Drug/ Medicine store- old office - KR")
		self.assertEqual(row["batch_no"], "DAIR-2026-00277")

	def test_a_row_that_names_no_store_leaves_it_blank(self):
		"""Blank means "wherever the settings say" — the posting falls back."""
		row = treatment_row({"drug_item": "LSK-SEMEN-TEST", "qty": 1})
		self.assertIsNone(row["source_warehouse"])
		self.assertIsNone(row["batch_no"])


from unittest.mock import patch

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

	def db_set(self, *a, **kw):
		pass


class Case:
	"""Enough Livestock Health Case for `post_drug_issue`."""

	def __init__(self, treatments):
		self.treatments = treatments
		self.animal = "ZZ-NOT-SAVED"
		self.name = "CASE-TEST"
		self.opened_by = None

	def get(self, key, default=None):
		return getattr(self, key, default)

	def db_set(self, *a, **kw):
		pass


class TestTheIssueUsesTheRowsStore(unittest.TestCase):
	"""The live breakage: every treatment came off one global store."""

	def _rows_posted(self, treatment):
		captured = []

		def fake_issue(rows, **kw):
			captured.extend(rows)
			return None

		case = Case([treatment])
		with patch.object(LHC.livestock_stock, "issue_items", side_effect=fake_issue), \
		     patch.object(LHC.livestock_stock, "drug_warehouse",
		                  return_value="Livestock Drug Store - KR"), \
		     patch.object(LHC.livestock_cost_center, "herd_of", return_value=None):
			LHC.LivestockHealthCase.post_drug_issue(case)
		return captured

	def test_it_issues_from_the_store_the_treatment_names(self):
		rows = self._rows_posted(
			Row(drug_item="LSK-SEMEN-TEST", qty=2, stock_entry_ref=None,
			    treatment_date=None, batch_no=None,
			    source_warehouse="Drug/ Medicine store- old office - KR")
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["warehouse"], "Drug/ Medicine store- old office - KR")

	def test_a_row_with_no_store_still_falls_back(self):
		"""Treatments recorded before this change have no store and must post."""
		rows = self._rows_posted(
			Row(drug_item="LSK-SEMEN-TEST", qty=1, stock_entry_ref=None,
			    treatment_date=None, batch_no=None, source_warehouse=None)
		)
		self.assertEqual(rows[0]["warehouse"], "Livestock Drug Store - KR")

	def test_the_batch_travels_with_the_row(self):
		rows = self._rows_posted(
			Row(drug_item="LSK-SEMEN-TEST", qty=1, stock_entry_ref=None,
			    treatment_date=None, batch_no="DAIR-2026-00277",
			    source_warehouse="Drug/ Medicine store- old office - KR")
		)
		self.assertEqual(rows[0]["batch_no"], "DAIR-2026-00277")
