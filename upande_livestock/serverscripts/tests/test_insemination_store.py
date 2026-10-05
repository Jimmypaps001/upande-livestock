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
use; its 63 semen items are in `Dairy Others`.

Both lookups are gone. The straws are `items_for_event("Service")`: the groups
the Service event type's stock rule names, searched across every store of the
company, the type's Default Store first. A straw is an ordinary items row with
its own `source_warehouse`, like a drug. The legacy straw fields
(`semen_item`/`semen_qty`/`semen_warehouse`) are still stored by an unticked
Service, but no longer post anything — the separate legacy straw issue that
read them was removed, with its tests.

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
from upande_livestock.serverscripts.tests.mapping_fixtures import (
	SEMEN_GROUP,
	ServiceIsMapped,
	ServiceIsUnmapped,
)
from upande_livestock.upande_livestock.doctype.livestock_event import livestock_event as LE


class TestTheStrawListIsNotPinnedToOneStore(unittest.TestCase):
	"""The regression that emptied the picker on live."""

	def _offered(self):
		seen = {}

		def fake_items_for_event(event_type, company=None):
			seen.setdefault("event_types", []).append(event_type)
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

		with patch.object(BO, "items_for_event", side_effect=fake_items_for_event):
			out = BO.breeding_options()
		return seen, out

	def test_the_straws_are_what_the_service_event_type_draws_on(self):
		"""Asked by event type, not by a store: items_for_event searches every
		store of the company, so nothing pins the lookup to one shelf."""
		seen, _out = self._offered()
		self.assertIn("Service", seen["event_types"])

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


class TestAnUntickedServicePostsNothing(ServiceIsUnmapped, unittest.TestCase):
	"""Live's shape: Service not ticked. The legacy straw fields are filled —
	the creator still writes them, and a calf's record reads its sire there —
	but there is no separate straw issue any more: nothing leaves the store."""

	def test_the_legacy_straw_is_not_issued(self):
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Service"
		doc.animal = "ZZ-NOT-SAVED"
		doc.event_date = frappe.utils.today()
		doc.semen_item = "Semen Delta Stormer"
		doc.semen_qty = 2
		doc.semen_warehouse = "Drug/ Medicine store- old office - KR"
		with patch.object(LE.livestock_stock, "issue_items") as issue:
			doc.post_stock_issue()
		issue.assert_not_called()
		self.assertEqual(doc.semen_item, "Semen Delta Stormer")


class TestAMappedSiteIssuesTheStrawOnTheTable(ServiceIsMapped, unittest.TestCase):
	"""The same facts again, on the configuration kaitet.local now runs.

	MAPPED: `Service -> Dairy Semen` exists, so the straw is an ordinary items
	row — `drug_issues` — like a vaccination's drug, and the three legacy fields
	are not read at all. It is the path the farm is on: the straw the operator
	chose, the store the operator chose (else the type's Default Store), the
	count the operator typed.

	`issue_items` is stubbed for the same reason as above: this is about the row
	handed to it, and a real Material Issue per assertion would draw down shared
	straws that other tests count.
	"""

	STRAW = "Semen Delta Stormer"
	CHOSEN = "Drug/ Medicine store- old office - KR"
	LEGACY_STORE = "Livestock Drug Store - KR"

	def _rows_for(self, *, qty=1, warehouse=CHOSEN):
		captured = []

		def fake_issue(rows, **kw):
			captured.extend(rows)
			return None

		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Service"
		doc.animal = "ZZ-NOT-SAVED"
		doc.event_date = frappe.utils.today()
		# The legacy fields are filled and must be ignored: a service entered on
		# a site that mapped Service after the fact can carry both, and the row
		# that is actually issued is the table's.
		doc.semen_item = "ZZ-LEGACY-STRAW"
		doc.semen_qty = 9
		doc.semen_warehouse = self.LEGACY_STORE
		doc.append(
			"drug_issues",
			{"item_code": self.STRAW, "qty": qty, "source_warehouse": warehouse, "uom": "Nos"},
		)

		with patch.object(LE.livestock_stock, "issue_items", side_effect=fake_issue), \
		     patch.object(LE.event_items, "default_store", return_value="ZZ Default Store"):
			doc.post_stock_issue()
		return captured

	def test_no_store_picked_falls_back_to_the_event_types_default_store(self):
		rows = self._rows_for(warehouse=None)
		self.assertEqual(rows[0]["warehouse"], "ZZ Default Store")
		self.assertNotEqual(rows[0]["warehouse"], self.LEGACY_STORE)

	def test_the_straw_on_the_table_is_the_straw_issued(self):
		rows = self._rows_for()
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item_code"], self.STRAW)
		self.assertNotEqual(
			rows[0]["item_code"],
			"ZZ-LEGACY-STRAW",
			"a mapped Service must not fall back to the legacy straw field",
		)

	def test_the_straw_is_issued_from_the_store_the_operator_picked(self):
		rows = self._rows_for()
		self.assertEqual(rows[0]["warehouse"], self.CHOSEN)
		self.assertNotEqual(rows[0]["warehouse"], self.LEGACY_STORE)

	def test_two_straws_takes_two(self):
		"""A double insemination in one session comes off the ledger twice."""
		rows = self._rows_for(qty=2)
		self.assertEqual(frappe.utils.flt(rows[0]["qty"]), 2)

	def test_the_mapping_is_what_chose_this_path(self):
		"""The three above are not reading a stubbed answer.

		The mixin pins the mapping ROWS; the real `consumes_items` reads them and
		the real branch in `post_stock_issue` follows. So what sent those rows
		down the table is the farm's mapping, exactly as it is on the site."""
		from upande_livestock.serverscripts.common import event_items as EI

		self.assertTrue(EI.consumes_items("Service"))
		self.assertEqual(EI.groups_for_event("Service"), [SEMEN_GROUP])
