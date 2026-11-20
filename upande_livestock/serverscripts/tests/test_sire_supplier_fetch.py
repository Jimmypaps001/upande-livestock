"""A semen sire's supplier is fetched from his straw Item, in a fixed order."""

import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from upande_livestock.serverscripts.common import sire_items as SI


class TestFetchOrder(unittest.TestCase):
	def _fetch(self, defaults=(), table=(), receipt=None, invoice=None, company="C1"):
		def get_all(doctype, **kw):
			if doctype == "Item Default":
				return [NS(company=c, default_supplier=s) for c, s in defaults]
			return [NS(supplier=s) for s in table][: kw.get("limit") or 99]

		def sql(q, args=None, as_dict=False):
			hit = receipt if "Purchase Receipt" in q else invoice
			return [NS(supplier=hit[0], posting_date=hit[1], creation=hit[1])] if hit else []

		with patch.object(SI.frappe, "get_all", side_effect=get_all), patch.object(SI.frappe.db, "sql", side_effect=sql):
			return SI.fetch_supplier("ITEM", company)

	def test_item_default_wins_and_this_companys_row_first(self):
		self.assertEqual(self._fetch(defaults=[("C2", "S-OTHER"), ("C1", "S-MINE")], table=["S-T"], receipt=("S-R", "2026-01-01")), "S-MINE")

	def test_item_supplier_table_next(self):
		self.assertEqual(self._fetch(table=["S-T"], receipt=("S-R", "2026-01-01")), "S-T")

	def test_latest_purchase_of_receipt_or_invoice(self):
		self.assertEqual(self._fetch(receipt=("S-R", "2026-01-01"), invoice=("S-I", "2026-03-01")), "S-I")

	def test_nothing_gives_none(self):
		self.assertIsNone(self._fetch())

	def test_no_item_gives_none(self):
		self.assertIsNone(SI.fetch_supplier(None))


class TestMigration(unittest.TestCase):
	def test_breed_matched_case_insensitively_unmatched_blank_and_supplier_fetched(self):
		from upande_livestock.patches import sire_breed_supplier_links as P
		sires = [NS(name="A", breed="holstein friesian", semen_item="I1", sire_type="Semen", supplier="typed"),
		         NS(name="B", breed="Unknown", semen_item=None, sire_type="Live bull", supplier=None)]
		sets = []
		with patch.object(P.frappe, "get_all", side_effect=lambda dt, **kw: ["Holstein Friesian"] if dt == "Breed" else sires), \
		     patch.object(P.frappe.db, "set_value", side_effect=lambda *a, **k: sets.append(a[1:])), \
		     patch.object(P, "fetch_supplier", return_value="S-1"):
			P.execute()
		self.assertIn(("A", "breed", "Holstein Friesian"), sets)
		self.assertIn(("A", "supplier", "S-1"), sets)
		self.assertIn(("B", "breed", None), sets)
