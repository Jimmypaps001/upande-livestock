"""A feed row is split across the batches that can actually cover it.

`batch_suggestion.allocate` states the contract in its own docstring:

    A single row on a Stock Entry carries one `batch_no`, so the caller
    normally uses the first pick AND SPLITS THE ROW when there is more than one.

`assign_batches` took `picks[0]` and left the row's FULL quantity on it. A line
needing 20,000 kg was given one batch holding 10,000 and told to consume 20,000
from it, which is how you get

    Batch No DAIR-2026-00037 of an Item 4040010086 has negative stock
    of quantity -20050.5 in the warehouse Feed Store - Concentrate store - KR

That batch is separately at net -32,381 in that store across 67 issues and no
receipts, which predates this code — but the rule above is what would keep
making new ones, and it is fixed here.

## And it blocks rather than falling through

A row the rule could not fill used to be left blank, on the reasoning that
ERPNext's own error naming the item is more use than a wrong batch. That is
true of the ERROR and false of what actually happens: with
`auto_create_serial_and_batch_bundle_for_outward` on, ERPNext does not error on
a blank row — it PICKS, by its own FIFO, and its FIFO is happy to choose a
batch the ledger does not back. That is how a batch reaches -32,381.

So a line that sound batches cannot cover now refuses, naming the item, the
store and the shortfall. It stops runs that used to limp through, deliberately.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import test_feed_batches_split as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import batches as B


class Row(dict):
	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError as e:
			raise AttributeError(k) from e

	def __setattr__(self, k, v):
		self[k] = v


class Doc:
	"""Enough Stock Entry for the splitter: rows in, rows replaced."""

	def __init__(self, rows):
		self.items = list(rows)

	def get(self, key):
		return self.items if key == "items" else None

	def set(self, key, value):
		if key == "items":
			self.items = list(value)


def _row(**kw):
	base = {"item_code": "Silage", "qty": 100.0, "s_warehouse": "W", "batch_no": "", "idx": 1}
	base.update(kw)
	return Row(**base)


POOL_KEY = ("Silage", "W")


class TestSplittingAcrossBatches(unittest.TestCase):
	def test_a_row_one_batch_can_cover_stays_one_row(self):
		rows = [_row(qty=40)]
		doc = Doc(rows)
		with patch.object(B, "_tracked_rows", return_value=rows), patch.object(
			B, "available_in_store", return_value={POOL_KEY: [{}]}
		), patch.object(
			B.batch_suggestion, "allocate",
			return_value={"picks": [{"batch_no": "B1", "qty": 40}], "short": 0.0},
		), patch.object(B.batch_suggestion, "is_placeholder", return_value=False):
			B.assign_batches(doc)
		self.assertEqual(len(doc.items), 1)
		self.assertEqual(doc.items[0]["batch_no"], "B1")
		self.assertEqual(doc.items[0]["qty"], 40)

	def test_a_row_needing_two_batches_becomes_two_rows(self):
		"""The bug, in one assertion. 20,000 off a batch holding 10,000 is how
		a batch goes to -32,381."""
		rows = [_row(qty=150)]
		doc = Doc(rows)
		with patch.object(B, "_tracked_rows", return_value=rows), patch.object(
			B, "available_in_store", return_value={POOL_KEY: [{}]}
		), patch.object(
			B.batch_suggestion, "allocate",
			return_value={
				"picks": [{"batch_no": "B1", "qty": 100}, {"batch_no": "B2", "qty": 50}],
				"short": 0.0,
			},
		), patch.object(B.batch_suggestion, "is_placeholder", return_value=False):
			B.assign_batches(doc)
		self.assertEqual([r["batch_no"] for r in doc.items], ["B1", "B2"])
		self.assertEqual([r["qty"] for r in doc.items], [100, 50])

	def test_the_split_adds_up_to_what_was_asked_for(self):
		"""Feed that leaves the store has to equal feed the run needed."""
		rows = [_row(qty=150)]
		doc = Doc(rows)
		with patch.object(B, "_tracked_rows", return_value=rows), patch.object(
			B, "available_in_store", return_value={POOL_KEY: [{}]}
		), patch.object(
			B.batch_suggestion, "allocate",
			return_value={
				"picks": [{"batch_no": "B1", "qty": 100}, {"batch_no": "B2", "qty": 50}],
				"short": 0.0,
			},
		), patch.object(B.batch_suggestion, "is_placeholder", return_value=False):
			B.assign_batches(doc)
		self.assertAlmostEqual(sum(r["qty"] for r in doc.items), 150)

	def test_every_split_row_keeps_the_rest_of_the_line(self):
		"""A copy that loses the warehouse posts against nothing."""
		rows = [_row(qty=150, uom="Kilogram", conversion_factor=1.0)]
		doc = Doc(rows)
		with patch.object(B, "_tracked_rows", return_value=rows), patch.object(
			B, "available_in_store", return_value={POOL_KEY: [{}]}
		), patch.object(
			B.batch_suggestion, "allocate",
			return_value={
				"picks": [{"batch_no": "B1", "qty": 100}, {"batch_no": "B2", "qty": 50}],
				"short": 0.0,
			},
		), patch.object(B.batch_suggestion, "is_placeholder", return_value=False):
			B.assign_batches(doc)
		for r in doc.items:
			self.assertEqual(r["s_warehouse"], "W")
			self.assertEqual(r["item_code"], "Silage")
			self.assertEqual(r["uom"], "Kilogram")
			self.assertTrue(r["use_serial_batch_fields"])

	def test_rows_that_already_name_a_batch_are_untouched(self):
		rows = [_row(qty=40, batch_no="CHOSEN")]
		doc = Doc(rows)
		with patch.object(B, "_tracked_rows", return_value=[]):
			B.assign_batches(doc)
		self.assertEqual(doc.items[0]["batch_no"], "CHOSEN")
		self.assertEqual(len(doc.items), 1)


class TestItBlocksInsteadOfFallingThrough(unittest.TestCase):
	"""A blank row is not a refusal. With
	`auto_create_serial_and_batch_bundle_for_outward` on, ERPNext PICKS — by a
	FIFO that will happily choose a batch the ledger does not back."""

	def test_nothing_in_the_store_refuses_and_says_which_item(self):
		rows = [_row(qty=40)]
		with patch.object(B, "_tracked_rows", return_value=rows), patch.object(
			B, "available_in_store", return_value={}
		), patch.object(
			B.batch_suggestion, "allocate", return_value={"picks": [], "short": 40.0}
		):
			with self.assertRaises(frappe.ValidationError) as caught:
				B.assign_batches(Doc(rows))
		msg = str(caught.exception)
		self.assertIn("Silage", msg)
		self.assertIn("W", msg)

	def test_a_partial_cover_refuses_too(self):
		"""Half a line issued is a run that looks done and is not."""
		rows = [_row(qty=150)]
		with patch.object(B, "_tracked_rows", return_value=rows), patch.object(
			B, "available_in_store", return_value={POOL_KEY: [{}]}
		), patch.object(
			B.batch_suggestion, "allocate",
			return_value={"picks": [{"batch_no": "B1", "qty": 100}], "short": 50.0},
		):
			with self.assertRaises(frappe.ValidationError) as caught:
				B.assign_batches(Doc(rows))
		self.assertIn("50", str(caught.exception))

	def test_the_refusal_is_not_swallowed(self):
		"""`assign_batches` catches everything else so a feed run is never lost
		to a helper having a bad day. The refusal must survive that."""
		rows = [_row(qty=40)]
		with patch.object(B, "_tracked_rows", return_value=rows), patch.object(
			B, "available_in_store", return_value={}
		), patch.object(
			B.batch_suggestion, "allocate", return_value={"picks": [], "short": 40.0}
		):
			with self.assertRaises(frappe.ValidationError):
				B.assign_batches(Doc(rows))

	def test_an_unrelated_failure_is_still_swallowed(self):
		rows = [_row(qty=40)]
		doc = Doc(rows)
		with patch.object(B, "_tracked_rows", side_effect=RuntimeError("boom")):
			self.assertEqual(B.assign_batches(doc), 0)


class TestWhatThePickerIsOffered(unittest.TestCase):
	"""The proposal the page shows before anything is posted."""

	def test_it_reports_a_pick_per_batch(self):
		with patch.object(
			B, "available_in_store",
			return_value={POOL_KEY: [{"batch_no": "B1", "qty": 100, "expiry_date": None}]},
		), patch.object(
			B.batch_suggestion, "allocate",
			return_value={"picks": [{"batch_no": "B1", "qty": 40}], "short": 0.0},
		):
			plan = B.suggest_batches([{"item_code": "Silage", "qty": 40, "warehouse": "W"}])
		self.assertEqual(plan[0]["item_code"], "Silage")
		self.assertEqual(plan[0]["picks"], [{"batch_no": "B1", "qty": 40}])
		self.assertEqual(plan[0]["short"], 0.0)

	def test_it_offers_every_batch_in_that_store(self):
		"""So the operator can choose one the rule did not propose."""
		pool = [
			{"batch_no": "B1", "qty": 100, "expiry_date": None},
			{"batch_no": "B2", "qty": 50, "expiry_date": None},
		]
		with patch.object(B, "available_in_store", return_value={POOL_KEY: pool}), patch.object(
			B.batch_suggestion, "allocate",
			return_value={"picks": [{"batch_no": "B1", "qty": 40}], "short": 0.0},
		):
			plan = B.suggest_batches([{"item_code": "Silage", "qty": 40, "warehouse": "W"}])
		self.assertEqual([b["batch_no"] for b in plan[0]["available"]], ["B1", "B2"])

	def test_a_line_with_nothing_says_so_rather_than_vanishing(self):
		with patch.object(B, "available_in_store", return_value={}), patch.object(
			B.batch_suggestion, "allocate", return_value={"picks": [], "short": 40.0}
		):
			plan = B.suggest_batches([{"item_code": "Silage", "qty": 40, "warehouse": "W"}])
		self.assertEqual(plan[0]["picks"], [])
		self.assertEqual(plan[0]["short"], 40.0)
		self.assertEqual(plan[0]["available"], [])
