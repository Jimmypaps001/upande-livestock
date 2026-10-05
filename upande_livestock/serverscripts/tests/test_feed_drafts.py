# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A herd fed today when the store is short: the feeding stands, the stock waits.

The run's Work Order is made and its transfer is saved as a draft; no mix and
no issue. The herd's timeline has the Feeding, the feed day screen counts the
herd as fed, and the Transactions page shows the run and posts it — transfer,
mix and issue — once the feed is in. A backdated short run still refuses.

The shortage is made, not found: a herd the stores CAN cover is told one of its
lines is short, so the run takes the waiting path, and posting it then really
moves the stock. That keeps the test off whatever the farm's stores hold today.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.feeding import _engine as feeding
from upande_livestock.serverscripts.feeding import feed_day_status
from upande_livestock.serverscripts.transactions._drafts import day_counts, draft_rows, entry_rows
from upande_livestock.serverscripts.transactions.post_stock_draft import post_stock_draft


def _coverable_herd():
	for h in frappe.get_all(
		"Herds",
		filters=[["bom", "is", "set"], ["number_of_animals", ">", 0]],
		fields=["name", "bom", "number_of_animals"],
		order_by="number_of_animals asc",
	):
		try:
			if feeding.get_herd_feeding_program(h.name)["can_manufacture"]:
				return h
		except frappe.ValidationError:
			continue
	return None


def _short(real):
	"""resolve_requirement, with its first line reported short."""

	def wrapped(*args, **kwargs):
		bom, lines = real(*args, **kwargs)
		lines = [dict(ln) for ln in lines]
		if lines:
			lines[0]["short_qty"] = lines[0]["required_qty"]
		return bom, lines

	return wrapped


class TestAShortFeedRunWaits(IntegrationTestCase):
	def setUp(self):
		self.herd = _coverable_herd()
		if not self.herd:
			raise unittest.SkipTest("no herd on this site can currently be manufactured")
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not self.employee:
			raise unittest.SkipTest("no active Employee on this site")

	def _run_short(self):
		with patch.object(feeding, "resolve_requirement", side_effect=_short(feeding.resolve_requirement)):
			res = feeding.manufacture_herd_feed(self.herd.name, employee=self.employee, portion=0.5)
		self.addCleanup(self._undo, res)
		return res

	def _undo(self, res):
		event = res.get("livestock_event")
		if event and frappe.db.get_value("Livestock Event", event, "docstatus") == 1:
			frappe.get_doc("Livestock Event", event).cancel()

	def test_the_feeding_is_recorded_and_the_transfer_waits_in_draft(self):
		frappe.flags.livestock_stock_drafts = []
		res = self._run_short()
		self.assertTrue(res["pending"])
		self.assertEqual(res["issue_stock_entry"], "")
		self.assertIn("Not enough to mix", res["waiting_for"])
		self.assertEqual(frappe.db.get_value("Work Order", res["work_order"], "docstatus"), 1)
		transfer = frappe.get_doc("Stock Entry", res["transfer_stock_entry"])
		self.assertEqual(transfer.docstatus, 0)
		self.assertEqual(transfer.purpose, "Material Transfer for Manufacture")
		# Not costed while it waits — an item never received has no rate.
		self.assertTrue(all(d.allow_zero_valuation_rate for d in transfer.items))
		# Nothing mixed, nothing issued.
		self.assertFalse(
			frappe.db.exists("Stock Entry", {"work_order": res["work_order"], "purpose": "Manufacture"})
		)
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.docstatus, 1)
		self.assertEqual(event.event_type, "Feeding")
		self.assertEqual(event.stock_entry, transfer.name)
		self.assertIn("waiting for stock", event.remarks)
		self.assertEqual([d["name"] for d in frappe.flags.livestock_stock_drafts], [transfer.name])

	def test_the_feed_day_screen_counts_the_herd_as_fed(self):
		item = frappe.db.get_value("BOM", self.herd.bom, "item")
		before = feed_day_status._issued_today(item, self.herd.name)
		res = self._run_short()
		after = feed_day_status._issued_today(item, self.herd.name)
		self.assertAlmostEqual(after - before, res["produced_qty"], places=4)

	def test_the_run_is_on_transactions_as_one_waiting_feed_run(self):
		res = self._run_short()
		row = next(r for r in draft_rows() if r["name"] == res["transfer_stock_entry"])
		self.assertEqual(row["label"], "Feed run · waiting to mix")
		self.assertEqual(row["source"]["name"], res["livestock_event"])
		self.assertEqual(row["source"]["herd"], self.herd.name)
		self.assertEqual(row["source"]["event_type"], "Feeding")
		self.assertGreaterEqual(day_counts(today(), today())[today()]["draft"], 1)

	def test_posting_it_transfers_mixes_and_issues(self):
		res = self._run_short()
		out = post_stock_draft({"name": res["transfer_stock_entry"]})
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(frappe.db.get_value("Stock Entry", res["transfer_stock_entry"], "docstatus"), 1)
		# Valued like any other entry once it posts.
		self.assertFalse(any(d.allow_zero_valuation_rate for d in frappe.get_doc("Stock Entry", res["transfer_stock_entry"]).items))
		mix = frappe.get_doc("Stock Entry", out["manufacture_stock_entry"])
		self.assertEqual(mix.docstatus, 1)
		self.assertEqual(mix.stock_entry_type, "Ration Mixing")
		issue = frappe.get_doc("Stock Entry", out["issue_stock_entry"])
		self.assertEqual(issue.docstatus, 1)
		self.assertEqual(issue.stock_entry_type, "Animal Feeding")
		self.assertAlmostEqual(issue.items[0].qty, res["produced_qty"], places=4)
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.stock_entry, issue.name)
		self.assertIn("Feed issued", event.remarks)
		# All three legs now show as posted on the day, the transfer included.
		posted = {e["name"]: e for e in entry_rows("AND se.posting_date = %(day)s", {"day": today()})}
		for name in (res["transfer_stock_entry"], mix.name, issue.name):
			self.assertEqual(posted[name]["status"], "Posted")
		self.assertEqual(posted[res["transfer_stock_entry"]]["label"], "Feed transfer")

	def test_posted_later_the_feed_still_counts_on_the_day_it_was_eaten(self):
		res = self._run_short()
		fed_on = add_days(today(), -1)
		# As if it had been fed yesterday and posted today.
		frappe.db.set_value("Stock Entry", res["transfer_stock_entry"], "posting_date", fed_on)
		out = post_stock_draft({"name": res["transfer_stock_entry"]})
		self.assertTrue(out.get("ok"), out)
		issue = frappe.get_doc("Stock Entry", out["issue_stock_entry"])
		self.assertEqual(str(issue.posting_date), today())
		self.assertTrue(issue.remarks.endswith(f" - fed {fed_on}"))
		item = frappe.db.get_value("BOM", self.herd.bom, "item")
		self.assertIn(issue.name, [r.name for r in feed_day_status._issues_on(item, self.herd.name, fed_on)])
		self.assertNotIn(issue.name, [r.name for r in feed_day_status._issues_on(item, self.herd.name, today())])

	def test_cancelling_the_feeding_drops_the_draft_and_the_work_order(self):
		res = self._run_short()
		frappe.get_doc("Livestock Event", res["livestock_event"]).cancel()
		self.assertFalse(frappe.db.exists("Stock Entry", res["transfer_stock_entry"]))
		self.assertEqual(frappe.db.get_value("Work Order", res["work_order"], "docstatus"), 2)


class TestABackdatedShortRunStillRefuses(IntegrationTestCase):
	def test_refused(self):
		herd = _coverable_herd()
		if not herd:
			raise unittest.SkipTest("no herd on this site has a BOM")
		with patch.object(feeding.backdate, "assert_allowed", return_value=None), \
		     patch(
		         "upande_livestock.serverscripts.feeding._availability.assert_can_cover_on",
		         side_effect=frappe.ValidationError("Not enough stock on that day"),
		     ):
			with self.assertRaises(frappe.ValidationError):
				feeding.manufacture_herd_feed(herd.name, posting_date=add_days(today(), -2))
