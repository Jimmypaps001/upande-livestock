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
