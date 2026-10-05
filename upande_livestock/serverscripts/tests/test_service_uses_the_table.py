"""A service consumes its straw through the same table as everything else.

Service had three bespoke fields and its own branch in `post_stock_issue`. They
carried exactly what the general table carries — item, quantity, store — plus a
batch they never had.

WHETHER A SERVICE POSTS IS ITS EVENT TYPE'S RULE, like every other type. A
ticked Service (Posts Stock Entry, with a straws group) issues its table rows,
a line with no store coming off the type's Default Store. An unticked Service
still stores what the creator wrote on the legacy straw fields — a calf's
record reads its sire there — but posts nothing: the separate legacy straw
issue is gone.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.tests.test_any_event_consumes import Doc, Row
from upande_livestock.upande_livestock.doctype.livestock_event import (
	livestock_event as LE,
)


class TestWhichPathAServiceTakes(unittest.TestCase):
	def _rows_posted(self, *, mapped, legacy_item=None, table_rows=None):
		captured = []

		def fake_issue(rows, **kw):
			captured.extend(rows)
			return None

		doc = Doc("Service", table_rows or [])
		doc.semen_item = legacy_item
		doc.semen_qty = 2
		doc.semen_warehouse = "Legacy Store - KR"
		with patch.object(LE.livestock_stock, "issue_items", side_effect=fake_issue), \
		     patch.object(LE.event_items, "default_store", return_value="Default Store - KR"), \
		     patch.object(LE.livestock_stock, "default_semen_item", return_value="DEFAULT-STRAW"), \
		     patch.object(LE.event_items, "consumes_items", return_value=mapped), \
		     patch.object(LE.backdate, "suppresses_stock", return_value=False):
			LE.LivestockEvent.post_stock_issue(doc)
		return captured

	def test_a_ticked_service_issues_through_the_table(self):
		rows = self._rows_posted(
			mapped=True,
			legacy_item="LEGACY-STRAW",
			table_rows=[Row(item_code="SEMEN-A", qty=3, uom="Nos",
			                source_warehouse="Drug/Medicine Store - Old Office - KR",
			                batch_no=None)],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item_code"], "SEMEN-A")
		self.assertEqual(rows[0]["qty"], 3)
		self.assertEqual(rows[0]["warehouse"], "Drug/Medicine Store - Old Office - KR")

	def test_a_ticked_service_line_with_no_store_uses_the_default_store(self):
		rows = self._rows_posted(
			mapped=True,
			table_rows=[Row(item_code="SEMEN-A", qty=1, uom="Nos", source_warehouse=None, batch_no=None)],
		)
		self.assertEqual([r["warehouse"] for r in rows], ["Default Store - KR"])

	def test_a_ticked_service_with_no_item_rows_issues_nothing_not_the_legacy_straw(self):
		"""Ticked but no line: the table is empty, and the straw fields must not
		quietly step in."""
		rows = self._rows_posted(mapped=True, legacy_item="LEGACY-STRAW", table_rows=[])
		self.assertEqual(rows, [])

	def test_an_unticked_service_issues_nothing_even_with_a_legacy_straw(self):
		"""The legacy straw path is gone: not ticked, nothing leaves the store —
		not the straw on the event, nor the Settings' default straw."""
		self.assertEqual(self._rows_posted(mapped=False, legacy_item="LSK-SEMEN-TEST"), [])
		self.assertEqual(self._rows_posted(mapped=False), [])


class FakeEvent:
	"""Just enough of a Livestock Event for the creator to fill and submit."""

	def __init__(self):
		self.rows = []
		self.semen_item = self.semen_qty = self.semen_warehouse = None
		self.name = "EV-FAKE"
		self.event_type = "Service"
		self.expected_calving_date = self.pregnancy_check_due_date = None
		self.stock_entry = None

	def append(self, table, row):
		self.rows.append(row)

	def insert(self): pass
	def submit(self): pass
	def reload(self): pass


class TestTheCreatorFollowsTheMapping(unittest.TestCase):
	PAYLOAD = {
		"animal": "A1", "semen_item": "STRAW-1", "semen_qty": 2, "semen_warehouse": "S1 - KR",
		"items": [{"item_code": "STRAW-1", "qty": 2, "source_warehouse": "S1 - KR", "batch_no": "B1"}],
	}

	def _create(self, mapped):
		from upande_livestock.serverscripts.breeding import create_service_event as CS
		doc = FakeEvent()
		with patch.object(CS, "guard"), \
		     patch.object(CS, "new_livestock_event", return_value=doc), \
		     patch.object(CS, "consumes_items", return_value=mapped, create=True), \
		     patch.object(CS, "append_items", side_effect=lambda d, p: d.append("drug_issues", p["items"][0]), create=True):
			out = CS.create_service_event(dict(self.PAYLOAD))
		self.assertTrue(out.get("ok"), out)
		return doc

	def test_a_mapped_site_writes_the_table_and_not_the_legacy_fields(self):
		doc = self._create(mapped=True)
		self.assertEqual(len(doc.rows), 1)
		self.assertIsNone(doc.semen_item)
		self.assertIsNone(doc.semen_warehouse)
		self.assertIsNone(doc.semen_qty)

	def test_an_unmapped_site_writes_the_legacy_fields_and_no_table(self):
		doc = self._create(mapped=False)
		self.assertEqual(doc.rows, [])
		self.assertEqual(doc.semen_item, "STRAW-1")
		self.assertEqual(doc.semen_qty, 2)
		self.assertEqual(doc.semen_warehouse, "S1 - KR")
