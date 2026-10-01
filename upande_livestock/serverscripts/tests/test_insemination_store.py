"""Choosing the straw, and the store it comes out of.

The Service form offered a "Straw used" select and nothing else — no store,
and no way to see where a straw was. On live that select was EMPTY, for the
two reasons the drug picker was empty before it (see test_drug_store_lookup),
neither of which anyone had applied to semen:

ONE, it searched a single store. `breeding_options` passed
`livestock_stock.semen_warehouse()` into `stock_items`, pinning the lookup to
`Livestock Drug Store - KR` — a warehouse with zero stocked bins. The straws
are in `Drug/Medicine Store - Old Office - KR` (217) and `Westwood Dairy
Store - KR` (144): 361 straws over 24 bins that the form could not see.

TWO, the item group fell back to the constant `DAIRY`, which live does not
use; its 63 semen items are in `Dairy Others`. That half is a setting, not
code, and is fixed on the site.

And having chosen a straw, the issue still came out of `semen_warehouse()`
whatever the operator picked, because a Service had nowhere to record a store.
A drug row has carried `source_warehouse` for exactly this reason; semen now
does the same.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import \
        test_insemination_store as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.breeding import breeding_options as BO


class TestTheStrawListIsNotPinnedToOneStore(unittest.TestCase):
	"""The regression that emptied the picker on live."""

	def _offered(self):
		seen = {}

		def fake_stock_items(kind, warehouse=None):
			seen["kind"] = kind
			seen["warehouse"] = warehouse
			# What the store actually holds, across two stores. A lookup
			# pinned to one of them can only ever return half of this.
			return [
				{"value": "4040030118", "label": "Semen Chico · 12 Nos in Westwood Dairy Store - KR",
				 "warehouse": "Westwood Dairy Store - KR",
				 "locations": [{"warehouse": "Westwood Dairy Store - KR", "qty": 12.0}]},
				{"value": "4040030119", "label": "Semen Usher · 30 Nos in Drug/Medicine Store - Old Office - KR",
				 "warehouse": "Drug/Medicine Store - Old Office - KR",
				 "locations": [{"warehouse": "Drug/Medicine Store - Old Office - KR", "qty": 30.0}]},
			]

		with patch.object(BO, "stock_items", side_effect=fake_stock_items):
			out = BO.breeding_options()
		return seen, out

	def test_every_configured_store_is_searched_not_just_the_semen_store(self):
		seen, _out = self._offered()
		self.assertEqual(seen["kind"], "semen")
		self.assertIsNone(
			seen["warehouse"],
			"the straw lookup must not be pinned to one store — that is what emptied it on live",
		)

	def test_the_straws_reach_the_page_with_their_stores_attached(self):
		_seen, out = self._offered()
		straws = out["semen_items"]
		self.assertEqual(len(straws), 2)
		self.assertEqual(
			{s["warehouse"] for s in straws},
			{"Westwood Dairy Store - KR", "Drug/Medicine Store - Old Office - KR"},
		)
		# The label is the whole point of the picker: a bare item code tells an
		# operator nothing about which straw it is or where to go for it.
		self.assertIn("Semen Chico", straws[0]["label"])


class TestTheEventCanRecordAStore(unittest.TestCase):
	def test_livestock_event_carries_a_semen_warehouse(self):
		meta = frappe.get_meta("Livestock Event")
		self.assertTrue(
			meta.has_field("semen_warehouse"),
			"a Service has nowhere to record the store the straw came out of",
		)
		field = meta.get_field("semen_warehouse")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Warehouse")


class TestTheChosenStoreReachesTheIssue(unittest.TestCase):
	"""Picking a store has to change where the straw comes from.

	kaitet.local carries the live shape: the real straws sit in
	`Drug/ Medicine store- old office - KR` while `semen_warehouse()` names
	`Livestock Drug Store - KR`. A Service that ignores the operator's choice
	asks the wrong shelf for stock it does not have.

	`issue_items` is stubbed rather than posted: this is about the row handed
	to it, and a real Material Issue per assertion would draw down shared
	straws that other tests count.
	"""

	STRAW = "Semen Delta Stormer"
	CHOSEN = "Drug/ Medicine store- old office - KR"

	def _rows_for(self, warehouse):
		captured = []

		def fake_issue(rows, **kw):
			captured.extend(rows)
			return None

		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Service"
		doc.animal = "ZZ-NOT-SAVED"
		doc.event_date = frappe.utils.today()
		doc.semen_item = self.STRAW
		doc.semen_qty = 1
		doc.semen_warehouse = warehouse

		from upande_livestock.upande_livestock.doctype.livestock_event import livestock_event as LE

		with patch.object(LE.livestock_stock, "issue_items", side_effect=fake_issue):
			doc.post_stock_issue()
		return captured

	def test_the_straw_is_issued_from_the_store_the_operator_picked(self):
		rows = self._rows_for(self.CHOSEN)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item_code"], self.STRAW)
		self.assertEqual(rows[0]["warehouse"], self.CHOSEN)

	def test_no_store_picked_falls_back_to_the_setting(self):
		"""Blank must keep behaving exactly as it did before the field existed."""
		from upande_livestock.serverscripts.common import stock as ST

		rows = self._rows_for(None)
		self.assertEqual(rows[0]["warehouse"], ST.semen_warehouse())


class TestHowManyStrawsTheSessionUsed(unittest.TestCase):
	"""The count on the event is the count taken out of the store.

	`semen_qty` has existed on the DocType since the start and the posting has
	always read it — but the Service form never rendered it, so it was always
	the default 1. A double insemination within one day is real practice
	(guards.py exempts Service from the same-day rule for exactly that reason),
	and the second straw came out of the flask without coming off the ledger.
	"""

	STRAW = "Semen Delta Stormer"
	CHOSEN = "Drug/ Medicine store- old office - KR"

	def _qty_issued(self, straws):
		captured = []

		def fake_issue(rows, **kw):
			captured.extend(rows)
			return None

		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Service"
		doc.animal = "ZZ-NOT-SAVED"
		doc.event_date = frappe.utils.today()
		doc.semen_item = self.STRAW
		doc.semen_qty = straws
		doc.semen_warehouse = self.CHOSEN

		from upande_livestock.upande_livestock.doctype.livestock_event import livestock_event as LE

		with patch.object(LE.livestock_stock, "issue_items", side_effect=fake_issue):
			doc.post_stock_issue()
		return captured[0]["qty"]

	def test_two_straws_takes_two(self):
		self.assertEqual(self._qty_issued(2), 2)

	def test_a_blank_count_still_takes_one(self):
		"""A Service that says nothing used a straw all the same."""
		self.assertEqual(self._qty_issued(0), 1)
