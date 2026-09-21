"""Naming the batch on a feed transfer, where nobody is there to name it.

Batch tracking is on for 105 Dairy Feed items, so the transfer a feed run posts
will not submit until every outgoing row of a tracked item names a batch — two
of the eight runs that failed in the week to 2026-09-21 failed on exactly that.
The quieter half is worse: of the 1,394 batched feed rows that did go through,
every single one carried a `-PREMIGRATION` batch, migration opening stock
holding trillions of invented units. No feed transfer has ever consumed a real
batch.

Spray puts a picker in front of a storesman. Feeding cannot: `_run_manufacture`
creates the transfer and submits it in the same breath, because the mix is eaten
before anyone would count it. So the rule decides here, and these tests pin what
it decides — especially the two things that must not change: a row someone
already filled is untouched, and a row that cannot be filled is left blank
rather than guessed at.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        from upande_livestock.serverscripts.tests import test_feed_batches as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

from upande_livestock.serverscripts.common import batches as B


class Row(dict):
	"""A Stock Entry Detail row: attributes for the code, dict for `.get`."""

	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError as e:
			raise AttributeError(k) from e

	def __setattr__(self, k, v):
		self[k] = v


class Doc:
	def __init__(self, rows):
		self._rows = rows

	def get(self, key):
		return self._rows if key == "items" else None


def row(item, qty, warehouse="Feed Store - Raw materials - KR", batch_no=""):
	return Row(item_code=item, qty=qty, s_warehouse=warehouse, batch_no=batch_no)


def batch(code, qty, expiry=None, created=None):
	return {"batch_no": code, "qty": qty, "expiry_date": expiry, "created": created}


class _Wired(unittest.TestCase):
	"""Stub the two things that touch the database, keep the rule real."""

	tracked = {"Limestone"}
	available: dict = {}

	def run_assign(self, doc):
		def fake_sql(q, params=None, **kw):
			return [(c, 1 if c in self.tracked else 0) for c in params["codes"]]

		with patch.object(B.frappe.db, "sql", side_effect=fake_sql), patch.object(
			B, "available_in_store", return_value=self.available
		), patch.object(B.frappe.utils, "today", return_value="2026-09-21"):
			return B.assign_batches(doc)


class TestWhatItFills(_Wired):
	def test_it_names_the_real_batch_not_the_migration_filler(self):
		"""The whole point. 1,394 feed rows took the placeholder before this."""
		self.available = {
			("Limestone", "Feed Store - Raw materials - KR"): [
				batch("4040010029-PREMIGRATION", 1000000236, created="2026-09-15"),
				batch("LIME-2026-0007", 400, created="2026-09-03"),
			]
		}
		r = row("Limestone", 50)
		self.assertEqual(self.run_assign(Doc([r])), 1)
		self.assertEqual(r.batch_no, "LIME-2026-0007")

	def test_it_takes_the_filler_when_that_is_genuinely_all_there_is(self):
		self.available = {
			("Limestone", "Feed Store - Raw materials - KR"): [
				batch("4040010029-PREMIGRATION", 1000000236, created="2026-09-15"),
			]
		}
		r = row("Limestone", 50)
		self.assertEqual(self.run_assign(Doc([r])), 1)
		self.assertEqual(r.batch_no, "4040010029-PREMIGRATION")

	def test_the_soonest_expiry_goes_first(self):
		self.available = {
			("Limestone", "Feed Store - Raw materials - KR"): [
				batch("LIME-LATE", 400, "2027-06-01"),
				batch("LIME-SOON", 400, "2026-10-05"),
			]
		}
		r = row("Limestone", 50)
		self.run_assign(Doc([r]))
		self.assertEqual(r.batch_no, "LIME-SOON")


class TestWhatItLeavesAlone(_Wired):
	def test_a_row_that_already_names_a_batch_is_untouched(self):
		self.available = {
			("Limestone", "Feed Store - Raw materials - KR"): [batch("LIME-NEW", 400)]
		}
		r = row("Limestone", 50, batch_no="LIME-CHOSEN-BY-HAND")
		self.assertEqual(self.run_assign(Doc([r])), 0)
		self.assertEqual(r.batch_no, "LIME-CHOSEN-BY-HAND")

	def test_an_untracked_item_is_left_blank(self):
		self.tracked = set()
		self.available = {}
		r = row("Molasses", 50)
		self.assertEqual(self.run_assign(Doc([r])), 0)
		self.assertEqual(r.batch_no, "")
		self.tracked = {"Limestone"}

	def test_an_incoming_row_is_not_touched(self):
		"""No source warehouse means stock arriving; ERPNext makes that batch."""
		r = Row(item_code="Limestone", qty=50, s_warehouse=None, batch_no="")
		self.assertEqual(self.run_assign(Doc([r])), 0)

	def test_a_row_with_no_stock_is_left_blank_not_guessed(self):
		"""ERPNext's own error naming the item is more use than a wrong batch
		that submits."""
		self.available = {}
		r = row("Limestone", 50)
		self.assertEqual(self.run_assign(Doc([r])), 0)
		self.assertEqual(r.batch_no, "")


class TestItNeverTakesTheFeedRunDown(_Wired):
	def test_a_failure_inside_the_helper_is_swallowed(self):
		"""A feed run must not be lost because the batch helper had a bad day."""
		r = row("Limestone", 50)
		with patch.object(B, "_tracked_rows", side_effect=RuntimeError("boom")):
			self.assertEqual(B.assign_batches(Doc([r])), 0)
		self.assertEqual(r.batch_no, "")

	def test_a_document_with_no_items_is_fine(self):
		self.assertEqual(self.run_assign(Doc([])), 0)


class TestSeveralRowsAtOnce(_Wired):
	def test_each_row_gets_its_own_store_answer(self):
		"""The same ingredient out of two stores is two different questions."""
		self.tracked = {"Limestone"}
		self.available = {
			("Limestone", "Feed Store - Raw materials - KR"): [batch("LIME-A", 400)],
			("Limestone", "Concentrate Mixing Store - KR"): [batch("LIME-B", 400)],
		}
		a = row("Limestone", 10)
		b = row("Limestone", 10, warehouse="Concentrate Mixing Store - KR")
		self.assertEqual(self.run_assign(Doc([a, b])), 2)
		self.assertEqual((a.batch_no, b.batch_no), ("LIME-A", "LIME-B"))
