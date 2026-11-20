"""Picking a sire brings his straw: the service issues it, a sire with none records without."""

import unittest
from unittest.mock import patch

from upande_livestock.serverscripts.common import livestock_sire as LS
from upande_livestock.serverscripts.tests.test_service_uses_the_table import FakeEvent

ITEMS = [("Semen Delta Stormer-F", "Semen Delta Stormer-F"), ("B-1", "Baymax Semen 14HO14919"),
         ("B-2", "Baymax Semen Sexed 14HO14919"), ("X", "Defroster")]


class TestSuggestion(unittest.TestCase):
	def test_by_code(self):
		self.assertEqual(LS.suggest_item("Baymax", "14HO14919", ITEMS), "B-1")

	def test_by_name_when_no_code(self):
		self.assertEqual(LS.suggest_item("Stormer", "", ITEMS), "Semen Delta Stormer-F")

	def test_nothing_for_an_unknown_bull(self):
		self.assertIsNone(LS.suggest_item("Zorro", "NL1234567", ITEMS))


class TestServiceTakesTheSiresStraw(unittest.TestCase):
	def _create(self, straw, sire_link="SIRE-1"):
		from upande_livestock.serverscripts.breeding import create_service_event as CS
		doc = FakeEvent()
		doc.sire_link = None
		sent = {}

		def fake_append(d, p):
			sent["items"] = p.get("items")
			for r in p.get("items") or []:
				d.append("drug_issues", r)

		with patch.object(CS, "guard"), \
		     patch.object(CS, "new_livestock_event", return_value=doc), \
		     patch.object(CS, "require_active", return_value=sire_link), \
		     patch.object(CS, "consumes_items", return_value=True), \
		     patch.object(CS, "today", return_value="2026-11-20"), \
		     patch.object(CS.frappe.db, "get_value", return_value=straw), \
		     patch.object(CS, "append_items", side_effect=fake_append):
			out = CS.create_service_event({"animal": "A1", "sire_link": sire_link})
		self.assertTrue(out.get("ok"), out)
		return doc

	def test_the_sire_with_a_straw_issues_one(self):
		doc = self._create("B-1")
		self.assertEqual(len(doc.rows), 1)
		self.assertEqual((doc.rows[0]["item_code"], doc.rows[0]["qty"]), ("B-1", 1))

	def test_the_sire_without_a_straw_records_without(self):
		self.assertEqual(self._create(None).rows, [])
