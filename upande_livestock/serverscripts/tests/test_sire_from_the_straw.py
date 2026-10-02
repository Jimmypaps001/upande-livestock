"""A calf's sire is the bull whose straw was used.

`record_birth` walks related_pregnancy -> Service and reads `svc.sire` — the
free-text box. An operator who picked a straw and left that box alone lost the
sire silently, and with the straw picker fixed that is now the common case
rather than the rare one.

`sire` is a Data field, so the straw's ITEM NAME goes in: "Semen Delta
Stormer", which is what a herdsman recognises on a calf's record. The item code
`4040030118` tells nobody anything.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.breeding import record_birth as RB


class Svc:
	def __init__(self, sire=None, semen_item=None, drug_issues=None):
		self.sire = sire
		self.semen_item = semen_item
		self.drug_issues = drug_issues or []
		self.event_type = "Service"

	def get(self, key, default=None):
		return getattr(self, key, default)


class Row(dict):
	def __getattr__(self, k):
		return self[k]


class TestWhereTheSireComesFrom(unittest.TestCase):
	def test_a_typed_sire_wins(self):
		svc = Svc(sire="Delta Stormer", semen_item="4040030118")
		self.assertEqual(RB._sire_of(svc), "Delta Stormer")

	def test_otherwise_it_is_the_straw_on_the_items_table(self):
		svc = Svc(drug_issues=[Row(item_code="4040030118")])
		with patch.object(RB.frappe.db, "get_value", return_value="Semen Delta Stormer"):
			self.assertEqual(RB._sire_of(svc), "Semen Delta Stormer")

	def test_then_the_legacy_straw_field(self):
		"""51 services recorded before the table hold their straw here."""
		svc = Svc(semen_item="4040030118")
		with patch.object(RB.frappe.db, "get_value", return_value="Semen Delta Stormer"):
			self.assertEqual(RB._sire_of(svc), "Semen Delta Stormer")

	def test_it_is_the_name_not_the_code(self):
		svc = Svc(semen_item="4040030118")
		with patch.object(RB.frappe.db, "get_value", return_value="Semen Delta Stormer"):
			self.assertNotEqual(RB._sire_of(svc), "4040030118")

	def test_a_service_with_neither_leaves_it_blank(self):
		self.assertEqual(RB._sire_of(Svc()), "")

	def test_the_items_table_beats_the_legacy_field(self):
		svc = Svc(semen_item="LEGACY", drug_issues=[Row(item_code="TABLE")])
		names = {"TABLE": "Semen From Table", "LEGACY": "Semen From Legacy"}
		with patch.object(RB.frappe.db, "get_value", side_effect=lambda dt, n, f: names[n]):
			self.assertEqual(RB._sire_of(svc), "Semen From Table")

	def test_a_failed_lookup_does_not_lose_the_straw(self):
		svc = Svc(semen_item="4040030118")
		with patch.object(RB.frappe.db, "get_value", side_effect=Exception("db down")):
			self.assertEqual(RB._sire_of(svc), "4040030118")
