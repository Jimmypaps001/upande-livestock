"""Why a store holding stock can still offer no batch.

The Feeding page reads its two columns from two different places. "Available"
is `Bin.actual_qty`. "Batch" is the bundle pool, which drops anything on a
DISABLED batch — `available_in_store` says `AND bt.disabled = 0`, and it is
right to, because ERPNext refuses to consume a disabled batch.

On live those two disagree, and the page showed the disagreement as a blank.
`Dry Cows  Meal` holds 48 kg in `Feed Store - Raw materials - KR`; all 48 sit
on `Dry Cows  Meal-PREMIGRATION`, one of 1,971 PREMIGRATION batches on that
site and every one of them disabled. So the row read "48 available" next to an
empty Batch cell, and the run then refused with a shortfall the operator could
not account for. Seven of the twenty stocked feed lines on live are in exactly
that state.

A blank is the one answer that cannot be acted on. Naming the batch that holds
the stock turns it into a job someone can do.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        from upande_livestock.serverscripts.tests import test_batch_blocked_reason as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

from upande_livestock.serverscripts.common import batches as B

STORE = "Feed Store - Raw materials - KR"


class _Wired(unittest.TestCase):
	"""Real rule, stubbed stores."""

	tracked = {"Dry Cows  Meal"}
	available: dict = {}
	held: dict = {}

	def suggest(self, lines):
		def fake_sql(q, params=None, **kw):
			return [(c, 1 if c in self.tracked else 0) for c in params["codes"]]

		with patch.object(B.frappe.db, "sql", side_effect=fake_sql), patch.object(
			B, "available_in_store", return_value=self.available
		), patch.object(
			B, "_held_on_disabled_batches", return_value=self.held
		), patch.object(B.frappe.utils, "today", return_value="2026-09-30"):
			return B.suggest_batches(lines)


class TestItNamesWhatHoldsTheStock(_Wired):
	def test_a_line_with_no_usable_batch_names_the_disabled_one(self):
		"""The live case: 48 kg, all of it on a disabled PREMIGRATION batch."""
		self.available = {}
		self.held = {
			("Dry Cows  Meal", STORE): [{"batch_no": "Dry Cows  Meal-PREMIGRATION", "qty": 48.0}]
		}
		line = self.suggest([{"item_code": "Dry Cows  Meal", "qty": 10, "warehouse": STORE}])[0]

		self.assertEqual(line["picks"], [])
		self.assertEqual(
			line["blocked_by"], [{"batch_no": "Dry Cows  Meal-PREMIGRATION", "qty": 48.0}]
		)

	def test_a_line_the_store_can_cover_reports_no_blocker(self):
		self.available = {
			("Dry Cows  Meal", STORE): [
				{"batch_no": "DAIR-2026-00467", "qty": 200.0, "expiry_date": None}
			]
		}
		self.held = {}
		line = self.suggest([{"item_code": "Dry Cows  Meal", "qty": 10, "warehouse": STORE}])[0]

		self.assertEqual(line["blocked_by"], [])
		self.assertEqual(line["picks"][0]["batch_no"], "DAIR-2026-00467")

	def test_an_untracked_item_is_never_blocked_by_a_batch(self):
		"""Silage is not batch tracked; a disabled batch is not its problem."""
		self.tracked = set()
		self.available = {}
		self.held = {("Silage", STORE): [{"batch_no": "SIL-OLD", "qty": 9.0}]}
		line = self.suggest([{"item_code": "Silage", "qty": 10, "warehouse": STORE}])[0]

		self.assertFalse(line["tracked"])
		self.assertEqual(line["blocked_by"], [])
		self.tracked = {"Dry Cows  Meal"}


class Row(dict):
	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError as e:
			raise AttributeError(k) from e

	def __setattr__(self, k, v):
		self[k] = v


class Doc:
	def __init__(self, rows):
		self._rows = list(rows)

	def get(self, key):
		return self._rows if key == "items" else None

	def set(self, key, value):
		if key == "items":
			self._rows = list(value)


class TestTheRefusalSaysWhy(_Wired):
	"""The page explains before the run; this explains during it.

	A run posted from the mobile round never passes the picker, so the throw is
	the only sentence that operator reads. "48 short in Feed Store" beside a
	store holding exactly 48 is the message that sent someone looking.
	"""

	def assign(self, doc):
		def fake_sql(q, params=None, **kw):
			return [(c, 1 if c in self.tracked else 0) for c in params["codes"]]

		with patch.object(B.frappe.db, "sql", side_effect=fake_sql), patch.object(
			B, "available_in_store", return_value=self.available
		), patch.object(
			B, "_held_on_disabled_batches", return_value=self.held
		), patch.object(B.frappe.utils, "today", return_value="2026-09-30"):
			return B.assign_batches(doc)

	def test_it_names_the_disabled_batch_holding_the_stock(self):
		self.available = {}
		self.held = {
			("Dry Cows  Meal", STORE): [{"batch_no": "Dry Cows  Meal-PREMIGRATION", "qty": 48.0}]
		}
		row = Row(item_code="Dry Cows  Meal", qty=10, s_warehouse=STORE, batch_no="")
		with self.assertRaises(B.frappe.ValidationError) as caught:
			self.assign(Doc([row]))
		self.assertIn("Dry Cows  Meal-PREMIGRATION", str(caught.exception))
		self.assertIn("disabled", str(caught.exception).lower())

	def test_an_empty_store_still_reads_as_an_empty_store(self):
		self.available = {}
		self.held = {}
		row = Row(item_code="Dry Cows  Meal", qty=10, s_warehouse=STORE, batch_no="")
		with self.assertRaises(B.frappe.ValidationError) as caught:
			self.assign(Doc([row]))
		self.assertNotIn("disabled", str(caught.exception).lower())
