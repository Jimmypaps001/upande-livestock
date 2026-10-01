"""An event that uses a batch-tracked item can say which batch.

`suggest_batches` has done this for feed since the batch work; nothing exposed
it to an event form, so an event consuming a batch-tracked drug could not post
— ERPNext refuses the Stock Entry for a mandatory batch and the screen has no
field to answer it.

This is the endpoint the Items table asks. It is the same question the Feeding
page asks, so it is the same rule and the same code; only the caller is new.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import item_batches as IB


class TestTheEndpointAnswersPerLine(unittest.TestCase):
	PLAN = [{
		"item_code": "DRUG-A", "warehouse": "General Store Karen - KR",
		"required_qty": 2.0, "tracked": True,
		"picks": [{"batch_no": "B-1", "qty": 2.0}],
		"short": 0.0, "blocked_by": [],
		"available": [{"batch_no": "B-1", "qty": 9.0, "expiry_date": None}],
	}]

	def test_it_asks_the_same_rule_feed_asks(self):
		with patch.object(IB, "suggest_batches", return_value=self.PLAN) as asked:
			out = IB.event_batches(frappe.as_json([
				{"item_code": "DRUG-A", "qty": 2, "warehouse": "General Store Karen - KR"}
			]))
		self.assertTrue(out["ok"])
		self.assertEqual(out["lines"], self.PLAN)
		asked.assert_called_once()

	def test_an_untracked_item_is_never_asked_for_a_batch(self):
		untracked = [dict(self.PLAN[0], tracked=False, picks=[], available=[])]
		with patch.object(IB, "suggest_batches", return_value=untracked):
			out = IB.event_batches(frappe.as_json([
				{"item_code": "DRUG-A", "qty": 2, "warehouse": "General Store Karen - KR"}
			]))
		self.assertFalse(out["lines"][0]["tracked"])

	def test_nothing_in_means_nothing_out(self):
		out = IB.event_batches(frappe.as_json([]))
		self.assertEqual(out["lines"], [])
