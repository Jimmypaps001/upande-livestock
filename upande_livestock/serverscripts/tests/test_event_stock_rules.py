# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Each Livestock Event Type carries its own stock rule.

Posts Stock Entry, its Item Groups, a Default Store and Must Name an Item live
on the event type (edited there, or all together on the Settings screen's Stock
tab through `settings.stock_rules`). They replaced a Settings table of
(event, group) rows, the drug/semen group and store settings, and the
`consumes_drugs` box, which disagreed with one another.

What is defended here:

* the rules are read off the event types (`event_items._rules` and the helpers
  over it), and an unticked type posts nothing;
* the picker offers the type's Default Store first;
* a line naming no store is issued from the type's Default Store; an unticked
  Service issues nothing, whatever its legacy straw fields say;
* "Must Name an Item" refuses to submit an event / health case / check-up that
  names nothing — but not a backdated record, a timeline mirror, or a Natural
  service;
* `save_stock_rules` refuses what it cannot honour and writes the rest onto the
  event type.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import event_items as EI
from upande_livestock.serverscripts.settings.stock_rules import stock_rules as stock_rules_endpoint
from upande_livestock.serverscripts.tests.test_any_event_consumes import Doc, Row
from upande_livestock.upande_livestock.doctype.livestock_diagnosis import livestock_diagnosis as LD
from upande_livestock.upande_livestock.doctype.livestock_event import livestock_event as LE
from upande_livestock.upande_livestock.doctype.livestock_health_case import livestock_health_case as LHC

EVENT_TYPE = "Livestock Event Type"

RULES = {
	"Calving": {"posts": True, "groups": ["Gloves", "DRUGS"], "default_store": "Clinic - KR", "must_name_item": True},
	"Vaccination": {"posts": True, "groups": ["DRUGS"], "default_store": None, "must_name_item": False},
}


def _leaf_item_group():
	return frappe.db.get_value("Item Group", {"is_group": 0}, "name", order_by="name asc")


def _leaf_warehouse():
	return frappe.db.get_value("Warehouse", {"is_group": 0, "disabled": 0}, "name", order_by="name asc")


class TestTheHelpersReadTheRules(unittest.TestCase):
	def setUp(self):
		p = patch.object(EI, "_rules", return_value=RULES)
		p.start()
		self.addCleanup(p.stop)

	def test_groups_come_from_the_rule_in_order(self):
		self.assertEqual(EI.groups_for_event("Calving"), ["Gloves", "DRUGS"])

	def test_the_mapping_rows_are_one_per_type_and_group(self):
		self.assertEqual(
			EI._mapping_rows(),
			[
				{"event_type": "Calving", "item_group": "Gloves"},
				{"event_type": "Calving", "item_group": "DRUGS"},
				{"event_type": "Vaccination", "item_group": "DRUGS"},
			],
		)
		self.assertTrue(EI.has_mapping())

	def test_default_store_and_must_name_item_are_per_type(self):
		self.assertEqual(EI.default_store("Calving"), "Clinic - KR")
		self.assertIsNone(EI.default_store("Vaccination"))
		self.assertTrue(EI.must_name_item("Calving"))
		self.assertFalse(EI.must_name_item("Vaccination"))

	def test_a_type_without_a_rule_posts_nothing_and_asks_nothing(self):
		self.assertEqual(EI.groups_for_event("Movement"), [])
		self.assertFalse(EI.consumes_items("Movement"))
		self.assertIsNone(EI.default_store("Movement"))
		self.assertFalse(EI.must_name_item("Movement"))
		self.assertEqual(EI.groups_for_event(None), [])

	def test_no_rules_at_all_means_no_mapping(self):
		with patch.object(EI, "_rules", return_value={}):
			self.assertFalse(EI.has_mapping())


class TestTheRulesAreReadOffTheEventTypes(unittest.TestCase):
	"""Unmocked: a real event type, created and deleted by the test."""

	NAME = "ZZ Stock Rule Test"

	def setUp(self):
		self.group = _leaf_item_group()
		self.store = _leaf_warehouse()
		if not (self.group and self.store):
			self.skipTest("no leaf item group or warehouse on this site")
		self.addCleanup(self._purge)
		self._purge()

	def _purge(self):
		frappe.db.delete("Livestock Event Type Item Group", {"parent": self.NAME, "parenttype": EVENT_TYPE})
		frappe.db.delete(EVENT_TYPE, {"name": self.NAME})
		frappe.db.commit()

	def _make(self, posts, must=0):
		doc = frappe.get_doc(
			{
				"doctype": EVENT_TYPE,
				"name": self.NAME,
				"is_active": 1,
				"posts_stock_entry": posts,
				"stock_item_groups": [{"item_group": self.group}, {"item_group": self.group}],
				"default_store": self.store,
				"must_name_item": must,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_a_ticked_type_is_read_with_its_groups_store_and_must(self):
		self._make(posts=1, must=1)
		rule = EI._rules()[self.NAME]
		self.assertEqual(
			rule, {"posts": True, "groups": [self.group], "default_store": self.store, "must_name_item": True}
		)
		self.assertTrue(EI.consumes_items(self.NAME))
		self.assertEqual(EI.default_store(self.NAME), self.store)
		self.assertTrue(EI.must_name_item(self.NAME))

	def test_an_unticked_type_has_no_rule_even_with_groups(self):
		self._make(posts=0, must=1)
		self.assertNotIn(self.NAME, EI._rules())
		self.assertFalse(EI.consumes_items(self.NAME))
		self.assertIsNone(EI.default_store(self.NAME))
		self.assertFalse(EI.must_name_item(self.NAME))


class TestThePickerOffersTheDefaultStoreFirst(unittest.TestCase):
	BALANCES = [
		{"name": "D1", "item_name": "Oxytet", "stock_uom": "Litre", "warehouse": "Big - KR", "qty": 40.0},
		{"name": "D1", "item_name": "Oxytet", "stock_uom": "Litre", "warehouse": "Default - KR", "qty": 2.0},
		{"name": "D2", "item_name": "Betamox", "stock_uom": "Vial", "warehouse": "Big - KR", "qty": 3.0},
	]

	def _items(self):
		rules = {"Vaccination": {"posts": True, "groups": ["DRUGS"], "default_store": "Default - KR", "must_name_item": False}}
		with patch.object(EI, "_rules", return_value=rules), \
		     patch.object(EI, "_company_warehouses", return_value=["Big - KR", "Default - KR"]), \
		     patch.object(EI, "_balances", return_value=self.BALANCES):
			return {i["value"]: i for i in EI.items_for_event("Vaccination", company="Karen Roses")}

	def test_the_default_store_leads_where_it_holds_the_item(self):
		d1 = self._items()["D1"]
		self.assertEqual([l["warehouse"] for l in d1["locations"]], ["Default - KR", "Big - KR"])
		self.assertEqual((d1["warehouse"], d1["qty"]), ("Default - KR", 2.0))
		self.assertIn("in Default - KR", d1["label"])

	def test_where_it_does_not_the_most_stocked_store_leads(self):
		d2 = self._items()["D2"]
		self.assertEqual(d2["warehouse"], "Big - KR")


class TestWhatAnEventIssues(unittest.TestCase):
	def _rows_posted(self, event_type, rows, *, consumes, store="Default - KR", legacy_item=None):
		captured = []
		doc = Doc(event_type, rows)
		doc.semen_item = legacy_item
		doc.semen_qty = 1
		doc.semen_warehouse = "Legacy - KR"
		with patch.object(LE.livestock_stock, "issue_items", side_effect=lambda r, **kw: captured.extend(r)), \
		     patch.object(LE.event_items, "consumes_items", return_value=consumes), \
		     patch.object(LE.event_items, "default_store", return_value=store), \
		     patch.object(LE.backdate, "suppresses_stock", return_value=False):
			LE.LivestockEvent.post_stock_issue(doc)
		return captured

	def test_a_ticked_events_line_with_no_store_uses_the_types_default_store(self):
		rows = self._rows_posted(
			"Vaccination",
			[Row(item_code="D1", qty=1, uom=None, source_warehouse=None, batch_no=None),
			 Row(item_code="D2", qty=1, uom=None, source_warehouse="Own - KR", batch_no=None)],
			consumes=True,
		)
		self.assertEqual([r["warehouse"] for r in rows], ["Default - KR", "Own - KR"])

	def test_an_unticked_service_issues_nothing(self):
		self.assertEqual(self._rows_posted("Service", [], consumes=False, legacy_item="STRAW"), [])

	def test_an_unticked_type_ignores_its_rows(self):
		rows = [Row(item_code="D1", qty=1, uom=None, source_warehouse="Own - KR", batch_no=None)]
		self.assertEqual(self._rows_posted("Vaccination", rows, consumes=False), [])


class TestAnEventMustNameAnItem(unittest.TestCase):
	def _event(self, event_type="Vaccination", items=(), **fields):
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = event_type
		for item in items:
			doc.append("drug_issues", {"item_code": item, "qty": 1})
		doc.update(fields)
		return doc

	def _check(self, doc, must=True):
		with patch.object(LE.event_items, "must_name_item", return_value=must):
			doc.require_named_item()

	def test_it_refuses_an_event_that_names_nothing(self):
		with self.assertRaises(frappe.ValidationError) as cm:
			self._check(self._event())
		self.assertIn("Vaccination", str(cm.exception))

	def test_a_row_with_no_item_does_not_count(self):
		with self.assertRaises(frappe.ValidationError):
			self._check(self._event(items=[None]))

	def test_an_item_row_passes(self):
		self._check(self._event(items=["D1"]))

	def test_off_by_default_it_asks_nothing(self):
		self._check(self._event(), must=False)

	def test_a_backdated_event_is_exempt(self):
		self._check(self._event(custom_is_backdated=1))

	def test_a_timeline_mirror_is_exempt(self):
		self._check(self._event(event_type="Check Up", reference_doctype="Livestock Diagnosis"))

	def test_a_natural_service_is_exempt(self):
		self._check(self._event(event_type="Service", service_type="Natural"))

	def test_an_ai_service_is_not(self):
		with self.assertRaises(frappe.ValidationError):
			self._check(self._event(event_type="Service", service_type="A.I."))

	def test_it_is_asked_on_submit(self):
		doc = self._event()
		with patch.object(LE.LivestockEvent, "require_named_item") as req:
			doc.before_submit()
		req.assert_called_once()


class TestAHealthCaseMustNameItsDrugs(unittest.TestCase):
	def _case(self, drugs, backdated=0):
		case = frappe.new_doc("Livestock Health Case")
		case.custom_is_backdated = backdated
		for drug in drugs:
			case.append("treatments", {"drug_item": drug, "qty": 1})
		return case

	def _check(self, case, must=True):
		with patch.object(LHC.event_items, "must_name_item", return_value=must) as m:
			case.require_named_drugs()
		return m

	def test_a_treatment_without_a_drug_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._check(self._case(["D1", None]))

	def test_every_treatment_naming_its_drug_passes(self):
		m = self._check(self._case(["D1", "D2"]))
		m.assert_called_with("Treatment")

	def test_off_it_asks_nothing(self):
		self._check(self._case([None]), must=False)

	def test_a_backdated_case_is_exempt(self):
		self._check(self._case([None], backdated=1))

	def test_a_case_with_no_treatments_passes(self):
		self._check(self._case([]))


class TestACheckUpMustNameAnItem(unittest.TestCase):
	def _diagnosis(self, items, backdated=0):
		doc = frappe.new_doc("Livestock Diagnosis")
		doc.custom_is_backdated = backdated
		for item in items:
			doc.append("drug_issues", {"item_code": item, "qty": 1})
		return doc

	def _check(self, doc, must=True):
		with patch.object(LD.event_items, "must_name_item", return_value=must) as m:
			doc.before_submit()
		return m

	def test_a_check_up_naming_nothing_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._check(self._diagnosis([]))

	def test_an_item_passes_and_the_check_up_rule_is_asked(self):
		m = self._check(self._diagnosis(["D1"]))
		m.assert_called_with("Check Up")

	def test_backdated_or_off_is_exempt(self):
		self._check(self._diagnosis([], backdated=1))
		self._check(self._diagnosis([]), must=False)


class TestSaveStockRules(unittest.TestCase):
	"""The Stock tab's save, against a real event type, restored afterwards.

	The endpoint rolls back on error and its saves are left to the request to
	commit, so each test restores the original rule and commits.
	"""

	TYPE = "Hoof Trimming"

	def setUp(self):
		from upande_livestock.serverscripts.settings import save_stock_rules as SR

		self.SR = SR
		if not frappe.db.exists(EVENT_TYPE, self.TYPE):
			self.skipTest(f"no {self.TYPE} event type on this site")
		self.group = _leaf_item_group()
		self.store = _leaf_warehouse()
		if not (self.group and self.store):
			self.skipTest("no leaf item group or warehouse on this site")
		doc = frappe.get_doc(EVENT_TYPE, self.TYPE)
		self.original = {
			"posts_stock_entry": doc.posts_stock_entry,
			"stock_item_groups": [r.item_group for r in doc.stock_item_groups],
			"default_store": doc.default_store,
			"must_name_item": doc.must_name_item,
		}
		self.addCleanup(self._restore)

	def _restore(self):
		frappe.db.rollback()
		doc = frappe.get_doc(EVENT_TYPE, self.TYPE)
		doc.posts_stock_entry = self.original["posts_stock_entry"]
		doc.set("stock_item_groups", [{"item_group": g} for g in self.original["stock_item_groups"]])
		doc.default_store = self.original["default_store"]
		doc.must_name_item = self.original["must_name_item"]
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

	def _save(self, **rule):
		return self.SR.save_stock_rules({"rules": [dict({"event_type": self.TYPE}, **rule)]})

	def _stored(self):
		doc = frappe.get_doc(EVENT_TYPE, self.TYPE)
		return (doc.posts_stock_entry, [r.item_group for r in doc.stock_item_groups],
		        doc.default_store, doc.must_name_item)

	def test_it_writes_the_rule_onto_the_event_type(self):
		res = self._save(posts_stock_entry=True, item_groups=[self.group, self.group],
		                 default_store=self.store, must_name_item=True)
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(res["changed"], [self.TYPE])
		self.assertEqual(self._stored(), (1, [self.group], self.store, 1))
		self.assertEqual(EI.default_store(self.TYPE), self.store)
		self.assertTrue(EI.must_name_item(self.TYPE))
		row = next(r for r in res["rules"] if r["event_type"] == self.TYPE)
		self.assertEqual(row["item_groups"], [self.group])

	def test_saving_the_same_rule_again_changes_nothing(self):
		self._save(posts_stock_entry=True, item_groups=[self.group], default_store=self.store)
		res = self._save(posts_stock_entry=True, item_groups=[self.group], default_store=self.store)
		self.assertEqual(res["changed"], [])

	def test_unticking_clears_groups_store_and_must(self):
		self._save(posts_stock_entry=True, item_groups=[self.group], default_store=self.store, must_name_item=True)
		res = self._save(posts_stock_entry=False, item_groups=[self.group], default_store=self.store,
		                 must_name_item=True)
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(self._stored(), (0, [], None, 0))

	def test_an_unknown_item_group_is_refused(self):
		before = self._stored()
		res = self._save(posts_stock_entry=True, item_groups=["ZZ No Such Group"])
		self.assertIn("ZZ No Such Group", res.get("error", ""))
		self.assertEqual(self._stored(), before)

	def test_an_unknown_store_is_refused(self):
		before = self._stored()
		res = self._save(posts_stock_entry=True, item_groups=[self.group], default_store="ZZ No Such Store")
		self.assertIn("ZZ No Such Store", res.get("error", ""))
		self.assertEqual(self._stored(), before)

	def test_posting_with_no_group_is_refused(self):
		before = self._stored()
		res = self._save(posts_stock_entry=True, item_groups=[])
		self.assertIn("names no item group", res.get("error", ""))
		self.assertEqual(self._stored(), before)

	def test_an_unknown_event_type_is_refused(self):
		res = self.SR.save_stock_rules({"rules": [{"event_type": "ZZ No Such Type"}]})
		self.assertIn("ZZ No Such Type", res.get("error", ""))

	def test_a_payload_without_rules_is_refused(self):
		self.assertIn("error", self.SR.save_stock_rules({}))

	def test_the_read_endpoint_lists_every_active_type_and_the_choices(self):
		res = stock_rules_endpoint()
		self.assertTrue(res.get("ok"), res)
		names = {r["event_type"] for r in res["rules"]}
		self.assertIn(self.TYPE, names)
		self.assertIn(self.group, res["item_groups"])
		self.assertIn(self.store, res["stores"])
