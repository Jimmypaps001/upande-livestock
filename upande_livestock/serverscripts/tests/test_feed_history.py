# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Livestock Feed History on a site: one record per herd-day, no stock, and cost per animal reading it.

The merge rules are tested without a site in `costing/test_maths.py`; this asks
what only a site can answer — the doctype's own validation, that saving one
posts nothing to the stores, that the report uses a history day only where
the ledger has no feed issue for it, and that the Rations page shows it marked.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from upande_livestock.serverscripts.costing import _data, _production
from upande_livestock.serverscripts.costing.cost_per_animal import report
from upande_livestock.serverscripts.feeding.ration_history import ration_history
from upande_livestock.serverscripts.tests.herd_fixture import cow_herd

#: A day far enough back that no real feeding or history is on it.
DAY = "2001-01-03"
DOCTYPE = "Livestock Feed History"


class TestFeedHistory(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.herd = cow_herd()
		self.item = frappe.db.get_value("Item", {"disabled": 0}, "name", order_by="name asc")
		if not (self.herd and self.item):
			self.skipTest("needs a herd and an item on the site")
		self._clear()
		self.addCleanup(self._clear)

	def _clear(self):
		for name in frappe.get_all(DOCTYPE, filters={"date": DAY}, pluck="name"):
			frappe.delete_doc(DOCTYPE, name, force=True, ignore_permissions=True)

	def _history(self, cost=None, head=40):
		return frappe.get_doc({
			"doctype": DOCTYPE, "date": DAY, "herd": self.herd, "head_count": head, "source": "Test",
			"total_cost": cost, "items": [{"item": self.item, "qty_kg": 100, "rate": 12.5}],
		}).insert(ignore_permissions=True)

	def test_totals_and_the_sheets_cost(self):
		doc = self._history()
		self.assertEqual(doc.items[0].amount, 1250)
		self.assertEqual(doc.total_kg, 100)
		self.assertEqual(doc.total_cost, 1250)          # blank: the lines added up
		doc.total_cost = 1400                            # the sheet's own figure wins
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value(DOCTYPE, doc.name, "total_cost"), 1400)

	def test_one_record_per_herd_and_day(self):
		self._history()
		with self.assertRaises(frappe.ValidationError):
			self._history()

	def test_saving_posts_no_stock(self):
		before = frappe.db.count("Stock Entry")
		self._history()
		self.assertEqual(frappe.db.count("Stock Entry"), before)

	def test_the_report_uses_history_where_the_ledger_has_none(self):
		self._history(cost=2000, head=40)
		day = getdate(DAY)
		with patch.object(_production, "installed", return_value=False):
			out = report(DAY, DAY)
		row = out["days"][0]
		self.assertTrue(row["feed_from_history"])
		self.assertEqual(row["history_feed_cost"], 2000)
		self.assertGreaterEqual(row["feed_cost"], 2000)
		herd = next(h for h in out["herds"] if h["herd"] == self.herd)
		self.assertEqual(herd["history_days"], 1)
		# Per head over the tracker's 40, not whatever the herd holds today.
		self.assertEqual(herd["days"][0]["heads"], 40)
		self.assertEqual(herd["days"][0]["feed_cost_per_head"], 50)

		# A feed issue on the ledger for the same herd-day wins; the history is not added on top.
		with patch.object(_production, "installed", return_value=False), \
			patch.object(_data, "feed_by_herd", return_value={self.herd: {day: 700.0}}):
			out = report(DAY, DAY)
		row = out["days"][0]
		self.assertFalse(row["feed_from_history"])
		self.assertEqual(row["history_feed_cost"], 0)
		herd = next(h for h in out["herds"] if h["herd"] == self.herd)
		self.assertEqual((herd["feed_cost"], herd["history_days"]), (700, 0))

	def test_the_rations_page_shows_history_marked(self):
		self._history(head=40)
		res = ration_history(herd=self.herd, from_date=DAY, to_date=DAY)
		self.assertTrue(res.get("ok"), res)
		rows = [r for r in res["rows"] if r["fed_on"] == DAY]
		self.assertEqual(len(rows), 1)
		row = rows[0]
		self.assertTrue(row["from_history"])
		self.assertEqual((row["bom_no"], row["qty"], row["uom"], row["heads"]), ("", 100, "Kg", 40))
		self.assertEqual([(ln["item_code"], ln["qty"]) for ln in row["lines"]], [(self.item, 100)])
		self.assertIn(self.herd, {h["herd"] for h in res["herds"]})

	def test_the_nutritionist_may_read_but_not_write(self):
		perm = {p.role: p for p in frappe.get_meta(DOCTYPE).permissions}
		self.assertTrue(perm["Livestock Nutritionist"].read)
		self.assertFalse(perm["Livestock Nutritionist"].write)
		self.assertTrue(perm["Livestock Manager"].write and perm["Livestock Manager"].delete)
		for role in ("Livestock Attendant", "Livestock Breeder", "Livestock Vet", "Livestock Stores"):
			self.assertTrue(perm[role].read)
			self.assertFalse(perm[role].write)
