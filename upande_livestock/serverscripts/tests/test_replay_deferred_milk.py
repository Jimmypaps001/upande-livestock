# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A backdated Milk Recording has a replay path.

`test_backdated_postings.py` proves a backdated recording posts nothing at
submit time. This proves the other half: `replay_deferred_milk` finds what it
deferred and posts it — on the recording's OWN date, not today's — exactly
once, and a record it cannot post is reported rather than silently dropped or
allowed to sink the rest of the batch.

Pinned on the Bin balance and the resulting documents, not on "nothing threw"
— the exact vacuous-green shape test_backdated_postings.py's own docstring
warns about.
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.milking.create_milk_recording import create_milk_recording
from upande_livestock.serverscripts.milking.replay_deferred_milk import replay_deferred_milk
from upande_livestock.upande_livestock.doctype.milk_recording.milk_recording import MilkRecording


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _bin_qty(item, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty"))


class TestReplayDeferredMilk(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(_set_window, 0)
		_set_window(1)
		self.item = frappe.db.get_single_value("Livestock Settings", "custom_milk_item")
		self.warehouse = frappe.db.get_single_value("Livestock Settings", "custom_milk_target_warehouse")
		if not (self.item and self.warehouse):
			self.skipTest("no milk item / target warehouse configured on this site")
		self.herd = frappe.db.get_value("Herds", {"custom_is_milking": 1}, "name") or frappe.db.get_value(
			"Herds", {}, "name"
		)
		if not self.herd:
			self.skipTest("no herd on this site")
		self.addCleanup(frappe.db.rollback)

	def _record(self, recording_date, yield_kg=120.0):
		res = create_milk_recording(
			{
				"herd": self.herd,
				"recording_date": recording_date,
				"total_yield_kg": yield_kg,
				"price_per_kg": 55.0,
				"milking_time": "06:00:00",
			}
		)
		self.assertNotIn("error", res, res.get("error"))
		return res

	def test_replay_posts_the_deferred_stock_and_moves_the_bin(self):
		before = _bin_qty(self.item, self.warehouse)
		res = self._record(add_days(today(), -70))
		doc = frappe.get_doc("Milk Recording", res["name"])
		self.assertFalse(doc.stock_entry, "setup created a live posting, not a deferred one")

		out = replay_deferred_milk({"name": res["name"]})
		self.assertNotIn("error", out, out.get("error"))
		self.assertEqual(out["failed"], [])
		self.assertEqual([p["name"] for p in out["posted"]], [res["name"]])

		doc.reload()
		self.assertTrue(doc.stock_entry, "replay must fill stock_entry — that is the idempotency guard")
		se = frappe.get_doc("Stock Entry", doc.stock_entry)
		self.assertEqual(se.docstatus, 1)
		# On the recording's own date, not today's — the whole point of a replay.
		self.assertEqual(str(se.posting_date), str(add_days(today(), -70)))
		self.assertEqual(_bin_qty(self.item, self.warehouse), before + 120.0)

	def test_replay_is_idempotent(self):
		res = self._record(add_days(today(), -71))
		first = replay_deferred_milk({"name": res["name"]})
		self.assertEqual(len(first["posted"]), 1)
		balance_after_first = _bin_qty(self.item, self.warehouse)

		second = replay_deferred_milk({"name": res["name"]})
		self.assertEqual(second["posted"], [])
		self.assertEqual(len(second["skipped"]), 1)
		self.assertEqual(second["skipped"][0]["reason"], "already posted")
		self.assertEqual(
			_bin_qty(self.item, self.warehouse), balance_after_first, "a second replay must not move stock again"
		)

	def test_replay_scopes_by_date_range(self):
		inside = self._record(add_days(today(), -10))
		outside = self._record(add_days(today(), -400))

		out = replay_deferred_milk(
			{"from_date": add_days(today(), -20), "to_date": add_days(today(), -5)}
		)
		self.assertNotIn("error", out, out.get("error"))
		posted_names = [p["name"] for p in out["posted"]]
		self.assertIn(inside["name"], posted_names)
		self.assertNotIn(outside["name"], posted_names)
		# The one outside the window is untouched, not merely unreported.
		self.assertFalse(frappe.db.get_value("Milk Recording", outside["name"], "stock_entry"))

	def test_replay_refuses_an_unbounded_call(self):
		"""No name and no range must not mean "post everything ever"."""
		out = replay_deferred_milk({})
		self.assertIn("error", out)

	def test_replay_skips_a_live_recording(self):
		"""A live recording already posted at submit time — replaying it must
		not touch stock a second time."""
		res = self._record(today())
		doc = frappe.get_doc("Milk Recording", res["name"])
		self.assertTrue(doc.stock_entry, "setup expected a live posting")

		out = replay_deferred_milk({"name": res["name"]})
		self.assertEqual(out["posted"], [])
		self.assertEqual(out["skipped"][0]["reason"], "already posted")

	def test_replay_collects_a_failure_without_aborting_the_batch(self):
		"""One record that cannot post must not sink the others in its batch."""
		good = self._record(add_days(today(), -30))["name"]
		bad = self._record(add_days(today(), -31))["name"]

		original = MilkRecording.post_stock_and_revenue

		def _boom(self):
			if self.name == bad:
				frappe.throw("forced failure for test")
			return original(self)

		with mock.patch.object(MilkRecording, "post_stock_and_revenue", _boom):
			out = replay_deferred_milk(
				{"from_date": add_days(today(), -35), "to_date": add_days(today(), -25)}
			)

		self.assertNotIn("error", out, out.get("error"))
		self.assertIn(good, [p["name"] for p in out["posted"]])
		failed_names = [f["name"] for f in out["failed"]]
		self.assertIn(bad, failed_names)
		self.assertTrue(frappe.db.get_value("Milk Recording", good, "stock_entry"))
		self.assertFalse(frappe.db.get_value("Milk Recording", bad, "stock_entry"))

	def test_a_live_milking_still_posts_untouched(self):
		"""The control: replay must not be the only path that works — a live
		submit still posts on its own, exactly as before."""
		before = _bin_qty(self.item, self.warehouse)
		self._record(today())
		self.assertEqual(_bin_qty(self.item, self.warehouse), before + 120.0)
