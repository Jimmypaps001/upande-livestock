# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""An event recorded today with nothing in the store stands; its issue waits.

And each event posts under its own Stock Entry Type ("Livestock Vaccination"),
and the Transactions page lists the waiting drafts and posts them once the
store can cover them.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.husbandry.create_husbandry_event import create_husbandry_event
from upande_livestock.serverscripts.tests.test_drug_issuing import _drug_store, _stocked_drug
from upande_livestock.serverscripts.tests.test_operations import _employee, _make_cow, _purge, _purge_events_for
from upande_livestock.serverscripts.transactions._drafts import draft_rows
from upande_livestock.serverscripts.transactions.post_stock_draft import post_stock_draft
from upande_livestock.serverscripts.transactions.stock_drafts import stock_drafts


class TestEachEventPostsUnderItsOwnName(IntegrationTestCase):
	def test_an_event_type_gets_livestock_and_its_name(self):
		name = livestock_stock.stock_entry_type_for("Drying Off")
		self.assertEqual(name, "Livestock Drying Off")
		self.assertEqual(frappe.db.get_value("Stock Entry Type", name, "purpose"), "Material Issue")

	def test_the_flows_that_are_not_events_keep_their_names(self):
		self.assertEqual(livestock_stock.stock_entry_type_for("Feeding"), "Animal Feeding")
		self.assertEqual(livestock_stock.stock_entry_type_for("Ration Manufacture"), "Ration Mixing")

	def test_an_unknown_kind_falls_back(self):
		self.assertEqual(livestock_stock.stock_entry_type_for("ZZ No Such Kind"), "Material Issue")

	def test_ticking_posts_stock_makes_the_type(self):
		name = "ZZ Draft Test Event"
		self.addCleanup(_purge, "Stock Entry Type", f"Livestock {name}")
		self.addCleanup(_purge, "Livestock Event Type", name)
		doc = frappe.new_doc("Livestock Event Type")
		doc.name = name
		doc.is_active = 1
		doc.insert(ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Stock Entry Type", f"Livestock {name}"))
		doc.posts_stock_entry = 1
		doc.save(ignore_permissions=True)
		self.assertTrue(frappe.db.exists("Stock Entry Type", f"Livestock {name}"))


class TestShortTodayLeavesADraft(IntegrationTestCase):
	def setUp(self):
		self.drug = _stocked_drug()
		if not self.drug:
			raise unittest.SkipTest("no drug stock on this site")
		self.cow = _make_cow("ZZ DRAFT COW")
		self.addCleanup(_purge, "Animal", self.cow.name)
		self.addCleanup(_purge_events_for, self.cow.name)

	def _record(self, qty):
		res = create_husbandry_event(
			{
				"event_type": "Deworming",
				"animal": self.cow.name,
				"operator": _employee(),
				"drugs": [{"item_code": self.drug.item_code, "qty": qty, "source_warehouse": _drug_store()}],
			}
		)
		self.assertFalse(res.get("error"), res.get("error"))
		if res.get("stock_entry") and frappe.db.exists("Stock Entry", res["stock_entry"]):
			self.addCleanup(self._drop_entry, res["stock_entry"])
		return res

	def _drop_entry(self, name):
		# The events point at the entry, so they go first.
		_purge_events_for(self.cow.name)
		if frappe.db.get_value("Stock Entry", name, "docstatus") == 1:
			frappe.get_doc("Stock Entry", name).cancel()
		_purge("Stock Entry", name)

	def test_the_event_stands_and_its_issue_is_a_draft(self):
		res = self._record(flt(self.drug.actual_qty) + 50)
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertEqual(event.docstatus, 1)
		self.assertEqual(event.stock_entry, res["stock_entry"])
		self.assertEqual(frappe.db.get_value("Stock Entry", res["stock_entry"], "docstatus"), 0)
		self.assertEqual(res["stock_drafts"][0]["stock_entry_type"], "Livestock Deworming")

	def test_a_covered_event_posts_and_says_nothing_about_drafts(self):
		res = self._record(1)
		self.assertEqual(frappe.db.get_value("Stock Entry", res["stock_entry"], "docstatus"), 1)
		self.assertNotIn("stock_drafts", res)

	def test_the_draft_is_on_the_transactions_list_with_its_event(self):
		res = self._record(flt(self.drug.actual_qty) + 50)
		row = next(r for r in draft_rows() if r["name"] == res["stock_entry"])
		self.assertEqual(row["source"]["name"], res["name"])
		self.assertEqual(row["source"]["animal"], self.cow.name)
		self.assertEqual(row["stock_entry_type"], "Livestock Deworming")
		self.assertFalse(row["can_post"])
		self.assertIn(self.drug.item_code, [i["item_code"] for i in row["items"]])
		out = stock_drafts()
		self.assertTrue(out.get("ok"), out)
		self.assertIn(res["stock_entry"], [d["name"] for d in out["drafts"]])

	def test_posting_is_refused_while_the_store_is_still_short(self):
		res = self._record(flt(self.drug.actual_qty) + 50)
		out = post_stock_draft({"name": res["stock_entry"]})
		self.assertIn("still cannot cover", out.get("error", ""))

	def test_once_the_store_can_cover_it_posts_today(self):
		res = self._record(flt(self.drug.actual_qty) + 50)
		# The store "caught up": the draft now asks for what is there.
		detail = frappe.get_value("Stock Entry Detail", {"parent": res["stock_entry"]}, "name")
		frappe.db.set_value("Stock Entry Detail", detail, {"qty": 1, "transfer_qty": 1})
		out = post_stock_draft({"name": res["stock_entry"]})
		self.assertTrue(out.get("ok"), out)
		se = frappe.get_doc("Stock Entry", res["stock_entry"])
		self.assertEqual(se.docstatus, 1)
		self.assertEqual(str(se.posting_date), today())

	def test_only_a_livestock_draft_can_be_posted_here(self):
		out = post_stock_draft({"name": "ZZ-NO-SUCH-ENTRY"})
		self.assertIn("not a livestock stock entry", out.get("error", ""))

	def test_cancelling_the_event_deletes_its_draft(self):
		res = self._record(flt(self.drug.actual_qty) + 50)
		frappe.get_doc("Livestock Event", res["name"]).cancel()
		self.assertFalse(frappe.db.exists("Stock Entry", res["stock_entry"]))
