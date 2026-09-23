"""The operator says which store a run draws from, and where it lands.

Every feed movement used to take its warehouses from Livestock Settings and
offer no say in it. `_run_manufacture` put both the WIP and the finished goods
in `_feed_store()`, and each ingredient came from whichever store
`_pick_source` liked best across the whole configured list. `_issue_feed` drew
the mix from `_feed_store()` and nothing else. That is right until the day it
is not — silage from the pit by the vegetable garden rather than the one below
the spray race, a concentrate mixed into a different store because the usual
one is full — and on that day there was nothing to do but change a setting for
everybody.

So both are choices now, and both default to exactly what they did before: a
caller that names nothing behaves as it always has.

## And the batch follows the store, which is the point

`common/batches.assign_batches` picks each row's batch out of `r.s_warehouse`.
Choosing a different source therefore changes which batches are on offer,
automatically — the two cannot disagree, because there is only one source of
truth for where the row comes from. That is asserted here rather than assumed,
because it is the kind of agreement that quietly stops holding.

`upande_scp` learned the other half of this the hard way (32dd07b): naming
`batch_no` is not enough on its own. With Stock Settings'
`auto_create_serial_and_batch_bundle_for_outward` on — it is 1 on this site AND
on live — ERPNext builds its own Serial and Batch Bundle by its own FIFO rule,
and the batch that was chosen is either replaced or the submit is refused
outright. The row has to say `use_serial_batch_fields` too.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import test_chosen_warehouse as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import batches as B
from upande_livestock.serverscripts.feeding import _engine


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
		self._rows = rows

	def get(self, key):
		return self._rows if key == "items" else None


class TestNamingTheSourceNarrowsTheSearch(unittest.TestCase):
	def test_a_named_store_is_the_only_candidate(self):
		"""Otherwise "draw it from the hay store" is a suggestion, not an
		instruction, and the run quietly takes it from somewhere else."""
		self.assertEqual(
			_engine._source_warehouses("Hay Store - Greenhouse - KR"),
			["Hay Store - Greenhouse - KR"],
		)

	def test_naming_nothing_searches_them_all_as_before(self):
		with patch.object(_engine, "_feed_source_warehouses", return_value=["A", "B"]):
			self.assertEqual(_engine._source_warehouses(None), ["A", "B"])
			self.assertEqual(_engine._source_warehouses(""), ["A", "B"])


class TestTheDestinationIsAChoiceToo(unittest.TestCase):
	def test_a_named_store_is_where_the_mix_lands(self):
		with patch.object(_engine, "_feed_store", return_value="Concentrate Mixing Store - KR"):
			self.assertEqual(
				_engine._target_warehouse("Feed Store - Concentrate store - KR"),
				"Feed Store - Concentrate store - KR",
			)

	def test_naming_nothing_lands_where_it_always_did(self):
		with patch.object(_engine, "_feed_store", return_value="Concentrate Mixing Store - KR"):
			self.assertEqual(_engine._target_warehouse(None), "Concentrate Mixing Store - KR")


class TestTheRunAcceptsBoth(unittest.TestCase):
	def test_manufacture_takes_a_source_and_a_target(self):
		import inspect

		p = inspect.signature(_engine._run_manufacture).parameters
		self.assertIn("source_warehouse", p)
		self.assertIn("target_warehouse", p)
		self.assertIsNone(p["source_warehouse"].default)
		self.assertIsNone(p["target_warehouse"].default)

	def test_the_concentrate_endpoint_passes_them_through(self):
		import inspect

		p = inspect.signature(_engine.manufacture_concentrate).parameters
		self.assertIn("source_warehouse", p)
		self.assertIn("target_warehouse", p)

	def test_feeding_takes_a_source(self):
		import inspect

		self.assertIn("source_warehouse", inspect.signature(_engine._issue_feed).parameters)


class TestTheBatchFollowsTheStore(unittest.TestCase):
	def test_batches_are_looked_for_in_the_row_s_own_warehouse(self):
		"""So choosing a source changes the batches on offer, with nothing
		else to keep in step."""
		asked = {}

		def spy(pairs):
			asked["pairs"] = pairs
			return {}

		rows = [Row(item_code="Silage", qty=10, s_warehouse="Silage Pit 2 below Spray Race - KR")]
		with patch.object(B, "available_in_store", side_effect=spy), patch.object(
			B, "_tracked_rows", return_value=rows
		):
			B.assign_batches(Doc(rows))
		self.assertEqual(asked["pairs"], [("Silage", "Silage Pit 2 below Spray Race - KR")])


class TestNamingTheBatchIsNotEnough(unittest.TestCase):
	"""`upande_scp` 32dd07b, measured on this same site.

	With `auto_create_serial_and_batch_bundle_for_outward` on, ERPNext builds
	its own bundle by FIFO for every outgoing row and then refuses the submit —
	"Serial and Batch Bundle ... has already created" — so the chosen batch is
	either replaced or the entry never leaves. The row must also say it is
	using the plain batch fields.
	"""

	def test_the_row_says_it_is_using_the_batch_fields(self):
		rows = [Row(item_code="Silage", qty=10, s_warehouse="W", batch_no="")]
		pool = {("Silage", "W"): [{"batch_no": "B1", "qty": 50, "expiry_date": None}]}
		with patch.object(B, "_tracked_rows", return_value=rows), patch.object(
			B, "available_in_store", return_value=pool
		), patch.object(
			B.batch_suggestion, "allocate", return_value={"picks": [{"batch_no": "B1"}]}
		), patch.object(B.batch_suggestion, "is_placeholder", return_value=False):
			B.assign_batches(Doc(rows))
		self.assertEqual(rows[0]["batch_no"], "B1")
		self.assertTrue(
			rows[0].get("use_serial_batch_fields"),
			"without this ERPNext replaces the pick by its own FIFO, or refuses the submit",
		)

	def test_a_row_it_could_not_fill_is_left_entirely_alone(self):
		"""Blank on purpose. A wrong batch that submits is worse than ERPNext's
		own refusal, which names the item."""
		rows = [Row(item_code="Silage", qty=10, s_warehouse="W", batch_no="")]
		with patch.object(B, "_tracked_rows", return_value=rows), patch.object(
			B, "available_in_store", return_value={}
		), patch.object(B.batch_suggestion, "allocate", return_value={"picks": []}):
			B.assign_batches(Doc(rows))
		self.assertEqual(rows[0]["batch_no"], "")
		self.assertIsNone(rows[0].get("use_serial_batch_fields"))

	def test_the_setting_that_makes_this_necessary_is_really_on(self):
		"""If this ever goes off, the flag is harmless rather than required —
		but it is on here and on live, so the need is real, not theoretical."""
		self.assertTrue(
			frappe.db.get_single_value(
				"Stock Settings", "auto_create_serial_and_batch_bundle_for_outward"
			)
		)


class TestThePageIsToldWhatItMayChoose(unittest.TestCase):
	"""A dropdown with nothing in it is not a choice. The stores come from the
	same list the run searches, so the page cannot offer one the engine would
	not look in."""

	def test_the_concentrate_endpoint_carries_the_stores(self):
		from upande_livestock.serverscripts.feeding.concentrates import concentrates

		res = concentrates()
		self.assertTrue(res.get("ok"), res)
		self.assertEqual(res["warehouses"], _engine._feed_source_warehouses())

	def test_it_carries_where_a_mix_lands_by_default(self):
		from upande_livestock.serverscripts.feeding.concentrates import concentrates

		self.assertEqual(concentrates()["default_target"], _engine._feed_store())

	def test_the_default_target_is_one_of_the_choices(self):
		"""Otherwise the form opens on a value its own dropdown cannot show."""
		from upande_livestock.serverscripts.feeding.concentrates import concentrates

		res = concentrates()
		self.assertIn(res["default_target"], res["warehouses"])
