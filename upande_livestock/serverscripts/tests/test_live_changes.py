# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""`livestock_changed`: one coalesced, ids-only broadcast per request."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common import live
from upande_livestock.serverscripts.tests.test_animal import make_dam

TAGS = ("TEST-LIVE-A", "TEST-LIVE-B", "TEST-LIVE-C")


class TestLiveChanges(IntegrationTestCase):
	def setUp(self):
		live.clear()
		self.pub = patch("frappe.publish_realtime").start()
		patch.object(live, "_audience", return_value=["a@example.com", "b@example.com"]).start()
		self.addCleanup(patch.stopall)
		self.addCleanup(live.clear)

	def calls(self):
		return [c for c in self.pub.call_args_list if c.args and c.args[0] == "livestock_changed"]

	def tearDown(self):
		for n in TAGS:
			if frappe.db.exists("Animal", n):
				frappe.delete_doc("Animal", n, force=True, ignore_permissions=True)

	def test_many_saves_publish_once_after_flush_with_every_name(self):
		for t in TAGS:
			make_dam(t)
		self.assertEqual(self.calls(), [])  # nothing goes out before the commit
		live.flush()
		animal_msgs = [c for c in self.calls() if c.args[1]["kind"] == "animal"]
		# one message per kind per user, not one per animal
		self.assertEqual(len(animal_msgs), 2)
		msg = animal_msgs[0].args[1]
		self.assertTrue(set(TAGS) <= set(msg["animals"]))
		self.assertEqual({c.kwargs["user"] for c in animal_msgs}, {"a@example.com", "b@example.com"})
		self.assertEqual(msg["doctype"], "Animal")
		self.assertFalse(msg["truncated"])

	def test_flush_clears_so_a_second_flush_is_silent(self):
		make_dam(TAGS[0])
		live.flush()
		self.pub.reset_mock()
		live.flush()
		self.assertEqual(self.calls(), [])

	def test_clear_on_rollback_publishes_nothing(self):
		make_dam(TAGS[0])
		live.clear()
		live.flush()
		self.assertEqual(self.calls(), [])

	def test_a_huge_batch_is_truncated_not_listed(self):
		doc = frappe._dict(doctype="Animal", name="x")
		for i in range(live.MAX_NAMES + 5):
			doc.name = f"A-{i}"
			live.note(doc)
		live.flush()
		msg = self.calls()[0].args[1]
		self.assertTrue(msg["truncated"])
		self.assertEqual(msg["names"], [])

	def test_publish_failure_never_raises(self):
		make_dam(TAGS[0])
		self.pub.side_effect = RuntimeError("redis down")
		live.flush()  # must not raise
		self.pub.side_effect = None

	def test_unrelated_doctype_and_foreign_stock_entry_are_ignored(self):
		live.note(frappe._dict(doctype="ToDo", name="x"))
		se = frappe._dict(doctype="Stock Entry", name="SE-1", stock_entry_type="Material Transfer", items=[])
		with patch.object(live, "_livestock_stores", return_value={"Kaitet Feed - K"}):
			live.note(se)
		live.flush()
		self.assertEqual(self.calls(), [])

	def test_livestock_stock_entry_is_broadcast_as_stock(self):
		se = frappe._dict(
			doctype="Stock Entry", name="SE-2", stock_entry_type="Livestock Vaccination", items=[]
		)
		live.note(se)
		live.flush()
		self.assertEqual(self.calls()[0].args[1]["kind"], "stock")
		se2 = frappe._dict(
			doctype="Stock Entry",
			name="SE-3",
			stock_entry_type="Material Issue",
			items=[frappe._dict(s_warehouse="Kaitet Feed - K")],
		)
		self.pub.reset_mock()
		with patch.object(live, "_livestock_stores", return_value={"Kaitet Feed - K"}):
			live.note(se2)
		live.flush()
		self.assertEqual(len(self.calls()), 2)
