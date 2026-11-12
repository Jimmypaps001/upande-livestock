# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""An item the store is short of can always be recorded: the issue becomes a draft.

Every stock-posting event takes the same path. Short today, or short on a past
day, or an item the stores hold none of at all: the record stands and its issue
is a draft Stock Entry that says what it waits on ("draft: store short on
<date>; post when stock is in"), a backdated one dated its own day and marked,
listed on the Transactions page and carried in the answer's `stock_drafts`.

An item with no stock has no store to name, so a line arriving with none takes
the event type's Default Store; with none set the event is refused naming the
setting.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import event_items
from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.common.envelope import run
from upande_livestock.serverscripts.husbandry.create_husbandry_event import create_husbandry_event
from upande_livestock.serverscripts.tests.test_operations import (
	_make_cow,
	_purge,
	_purge_events_for,
)
from upande_livestock.serverscripts.transactions._drafts import draft_rows

TYPE = "Deworming"
ITEM = "ZZ-NO-STOCK-DRUG"


def _employee():
	return frappe.db.get_value("Employee", {"status": "Active"}, "name")


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _drop_item():
	frappe.db.delete("Item", {"name": ITEM})
	frappe.db.commit()


def _unstocked_item():
	"""An item in the event's group that no store has ever held."""
	groups = event_items.groups_for_event(TYPE)
	if not groups:
		raise unittest.SkipTest("Deworming draws on no item group here")
	_drop_item()
	frappe.get_doc({
		"doctype": "Item", "item_code": ITEM, "item_name": ITEM, "item_group": groups[0],
		"stock_uom": "Nos", "is_stock_item": 1,
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	return ITEM


class StockCase(IntegrationTestCase):
	def setUp(self):
		if not _employee() or not event_items.default_store(TYPE):
			raise unittest.SkipTest("no employee or no Deworming default store on this site")
		self.item = _unstocked_item()
		self.addCleanup(_drop_item)
		self.store = event_items.default_store(TYPE)
		self.cow = _make_cow("ZZ NOSTOCK COW")
		self.addCleanup(_purge, "Animal", self.cow.name)
		self.addCleanup(_purge_events_for, self.cow.name)
		self.addCleanup(_set_window, 0)
		self.drafts = []
		self.addCleanup(self._drop_drafts)

	def _drop_drafts(self):
		_purge_events_for(self.cow.name)
		for name in self.drafts:
			if frappe.db.exists("Stock Entry", name):
				_purge("Stock Entry", name)

	def _round(self, when=None, store="default", **extra):
		row = {"item_code": self.item, "qty": 2}
		if store == "default":
			row["source_warehouse"] = self.store
		elif store:
			row["source_warehouse"] = store
		res = create_husbandry_event({
			"event_type": TYPE, "animal": self.cow.name, "operator": _employee(),
			"event_date": when, "drugs": [row], **extra,
		})
		if res.get("stock_entry"):
			self.drafts.append(res["stock_entry"])
		return res


class TestTodaysShortageIsADraftThatSaysSo(StockCase):
	def test_the_draft_names_the_event_and_what_it_waits_on(self):
		res = self._round()
		self.assertFalse(res.get("error"), res.get("error"))
		se = frappe.get_doc("Stock Entry", res["stock_entry"])
		self.assertEqual(se.docstatus, 0)
		self.assertIn("Livestock Deworming", se.remarks)
		self.assertIn("draft: store short on", se.remarks)
		self.assertIn("post when stock is in", se.remarks)
		self.assertFalse(se.remarks.startswith(livestock_stock.BACKDATED_PREFIX))

	def test_the_answer_carries_stock_drafts(self):
		res = self._round()
		self.assertEqual([d["name"] for d in res["stock_drafts"]], [res["stock_entry"]])
		self.assertIn("need", res["stock_drafts"][0]["short"])

	def test_it_is_listed_on_transactions_and_not_as_backdated(self):
		res = self._round()
		row = next(r for r in draft_rows() if r["name"] == res["stock_entry"])
		self.assertFalse(row["backdated"])


class TestABackdatedShortageIsADraftToo(StockCase):
	def setUp(self):
		super().setUp()
		_set_window(1)
		self.day = add_days(today(), -40)

	def test_issue_items_drafts_a_short_past_day_dated_that_day(self):
		name = livestock_stock.issue_items(
			[{"item_code": self.item, "qty": 3, "warehouse": self.store}],
			remarks="Livestock Deworming - test", posting_date=self.day, employee=_employee(),
			what=TYPE, draft_if_short=True,
		)
		self.drafts.append(name)
		se = frappe.get_doc("Stock Entry", name)
		self.assertEqual(se.docstatus, 0)
		self.assertEqual(str(se.posting_date), self.day)
		self.assertEqual(se.set_posting_time, 1)
		self.assertTrue(se.posting_time)
		self.assertTrue(se.remarks.startswith(livestock_stock.BACKDATED_PREFIX))
		self.assertIn("draft: store short on", se.remarks)

	def test_without_the_draft_flag_it_still_refuses(self):
		with self.assertRaises(frappe.ValidationError):
			livestock_stock.issue_items(
				[{"item_code": self.item, "qty": 3, "warehouse": self.store}],
				remarks="x", posting_date=self.day, employee=_employee(), what=TYPE,
			)

	def test_a_backdated_round_short_on_its_day_is_a_marked_draft(self):
		res = self._round(self.day)
		self.assertFalse(res.get("error"), res.get("error"))
		se = frappe.get_doc("Stock Entry", res["stock_entry"])
		self.assertEqual((se.docstatus, str(se.posting_date)), (0, self.day))
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertEqual(event.stock_entry, se.name)
		# The placeholder IS the posting: nothing is left for a reconciliation.
		self.assertFalse(event.get("custom_unposted_drugs"))
		self.assertEqual([d["name"] for d in res["stock_drafts"]], [se.name])

	def test_the_transactions_list_flags_it_backdated(self):
		res = self._round(self.day)
		row = next(r for r in draft_rows() if r["name"] == res["stock_entry"])
		self.assertTrue(row["backdated"])
		self.assertEqual(row["source"]["name"], res["name"])

	def test_a_backdated_round_the_store_had_stays_unposted_with_no_draft(self):
		with patch.object(livestock_stock, "check_availability", return_value=[]):
			res = self._round(self.day)
		self.assertFalse(res.get("error"), res.get("error"))
		self.assertEqual(res.get("stock_entry"), "")
		self.assertNotIn("stock_drafts", res)
		self.assertEqual(frappe.db.get_value("Livestock Event", res["name"], "custom_unposted_drugs"), 1)


class TestAnItemWithNoStockCanBePicked(StockCase):
	def test_the_picker_lists_it_after_the_held_items_marked_out_of_stock(self):
		items = event_items.items_for_event(TYPE)
		mine = next(i for i in items if i["value"] == self.item)
		self.assertFalse(mine["in_stock"])
		self.assertEqual(mine["locations"], [])
		self.assertEqual(mine["qty"], 0)
		self.assertEqual(mine["uom"], "Nos")
		self.assertEqual(mine["warehouse"], self.store)
		flags = [i["in_stock"] for i in items]
		self.assertEqual(flags, sorted(flags, reverse=True), "in-stock items come first")
		self.assertTrue(all(i["in_stock"] is True for i in items if i["locations"]))

	def test_items_by_event_carries_it(self):
		self.assertIn(self.item, [i["value"] for i in event_items.items_by_event()[TYPE]])

	def test_the_health_and_event_options_carry_the_flag(self):
		from upande_livestock.serverscripts.health.health_options import health_options
		from upande_livestock.serverscripts.movement.event_options import event_options

		for res in (event_options(), health_options()):
			self.assertNotIn("error", res, res.get("error"))
			rows = res["items_by_event"][TYPE]
			self.assertTrue(all("in_stock" in r and "locations" in r for r in rows))
			self.assertIn(self.item, [r["value"] for r in rows if not r["in_stock"]])

	def test_husbandry_options_carry_it(self):
		from upande_livestock.serverscripts.husbandry.husbandry_options import husbandry_options

		res = husbandry_options()
		self.assertNotIn("error", res, res.get("error"))
		mine = next(i for i in res["drug_items"] if i["value"] == self.item)
		self.assertFalse(mine["in_stock"])


class TestALineWithNoStoreTakesTheDefaultStore(StockCase):
	def test_the_server_fills_the_event_types_default_store(self):
		res = self._round(store=None)
		self.assertFalse(res.get("error"), res.get("error"))
		se = frappe.get_doc("Stock Entry", res["stock_entry"])
		self.assertEqual(se.items[0].s_warehouse, self.store)

	def test_with_no_default_store_set_it_refuses_naming_the_setting(self):
		with patch.object(event_items, "default_store", return_value=None):
			res = self._round(store=None)
		self.assertIn("Default Store", res.get("error") or "")
		self.assertIn(TYPE, res["error"])

	def test_issue_items_takes_the_default_store_for_a_bare_row(self):
		name = livestock_stock.issue_items(
			[{"item_code": self.item, "qty": 1, "warehouse": None}],
			remarks="x", employee=_employee(), what=TYPE, draft_if_short=True,
		)
		self.drafts.append(name)
		self.assertEqual(frappe.get_doc("Stock Entry", name).items[0].s_warehouse, self.store)

	def test_store_for_prefers_the_named_store(self):
		self.assertEqual(event_items.store_for(TYPE, "Some Store - X", self.item), "Some Store - X")


class TestEveryEventKindDraftsWhenShort(StockCase):
	"""The straw, the sealant, the drug: each kind of event goes down one path."""

	def _event(self, event_type, group_item=None, **fields):
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = event_type
		doc.animal = self.cow.name
		doc.event_date = today()
		doc.operator = _employee()
		for k, v in fields.items():
			doc.set(k, v)
		return doc

	def test_a_drying_off_event_posts_its_sealant_as_a_draft(self):
		if not event_items.consumes_items("Drying Off"):
			self.skipTest("Drying Off posts no stock here")
		group = event_items.groups_for_event("Drying Off")[0]
		frappe.db.set_value("Item", self.item, "item_group", group)
		store = event_items.default_store("Drying Off")
		if not store:
			self.skipTest("no Drying Off default store")
		from upande_livestock.serverscripts.breeding.create_drying_off_event import create_drying_off_event

		res = create_drying_off_event({
			"animal": self.cow.name, "operator": _employee(),
			"items": [{"item_code": self.item, "qty": 1}],
		})
		if res.get("stock_entry"):
			self.drafts.append(res["stock_entry"])
		self.assertFalse(res.get("error"), res.get("error"))
		self.assertEqual(frappe.db.get_value("Stock Entry", res["stock_entry"], "docstatus"), 0)
		self.assertTrue(res.get("stock_drafts"))

	def test_a_service_straw_with_no_stock_is_a_draft(self):
		if not event_items.consumes_items("Service"):
			self.skipTest("Service posts no stock here")
		group = event_items.groups_for_event("Service")[0]
		frappe.db.set_value("Item", self.item, "item_group", group)
		from upande_livestock.serverscripts.breeding.create_service_event import create_service_event

		res = create_service_event({
			"animal": self.cow.name, "operator": _employee(), "service_type": "A.I.",
			"items": [{"item_code": self.item, "qty": 1}],
		})
		if res.get("stock_entry"):
			self.drafts.append(res["stock_entry"])
		self.assertFalse(res.get("error"), res.get("error"))
		self.assertEqual(frappe.db.get_value("Stock Entry", res["stock_entry"], "docstatus"), 0)
		self.assertTrue(res.get("stock_drafts"))


class TestTheEnvelopeReportsDraftsFromNestedCalls(IntegrationTestCase):
	def test_only_the_outermost_run_collects_the_drafts(self):
		se = frappe._dict(name="SE-FAKE", stock_entry_type="Livestock Test")

		def inner():
			livestock_stock.note_draft_message(se, "short")
			return {"ok": True}

		holder = {}

		def outer():
			holder["inner"] = run(inner, "inner")
			return {"ok": True}

		res = run(outer, "outer")
		self.assertNotIn("stock_drafts", holder["inner"])
		self.assertEqual([d["name"] for d in res["stock_drafts"]], ["SE-FAKE"])


class TestIssueFeedIsADraftWhenShort(IntegrationTestCase):
	def setUp(self):
		from upande_livestock.serverscripts.tests.test_feed_drafts import _coverable_herd

		self.herd = _coverable_herd()
		self.employee = _employee()
		if not (self.herd and self.employee):
			raise unittest.SkipTest("no herd the stores can feed")
		self.addCleanup(frappe.db.rollback)

	def test_a_short_issue_is_a_draft_and_the_feeding_stands(self):
		from upande_livestock.serverscripts.feeding.issue_feed import issue_feed

		short = [{"item_code": "X", "item_name": "Feed", "warehouse": "W", "required": 5, "available": 0,
		          "short": 5, "uom": "Kg"}]
		with patch.object(livestock_stock, "check_availability", return_value=short):
			res = issue_feed(self.herd.name, 5, employee=self.employee)
		self.assertFalse(res.get("error"), res.get("error"))
		self.assertTrue(res["pending"])
		self.assertEqual(frappe.db.get_value("Stock Entry", res["stock_entry"], "docstatus"), 0)
		self.assertEqual(res["stock_drafts"][0]["name"], res["stock_entry"])
		remarks = frappe.db.get_value("Stock Entry", res["stock_entry"], "remarks")
		self.assertIn("draft: store short on", remarks)
		self.assertTrue(remarks.startswith("Animal feeding - " + self.herd.name))
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.stock_entry, res["stock_entry"])
		row = next(r for r in draft_rows() if r["name"] == res["stock_entry"])
		self.assertEqual(row["source"]["name"], event.name)
