"""Which item groups an event type may consume, as a list of any length.

`stock_items` knew exactly two kinds, "drug" and "semen", each resolving to one
item group through a constant in the source. A Calving that uses gloves,
lubricant, a bolus and an antiseptic had nowhere to say so, and the farm could
not add one without a deploy.

The mapping is unbounded in both directions: an event type may have no rows,
one, four or seven, and rows are added and removed freely.
"""

import unittest

import frappe


class TestTheMappingExists(unittest.TestCase):
	def test_livestock_settings_carries_the_table(self):
		meta = frappe.get_meta("Livestock Settings")
		field = meta.get_field("custom_event_item_groups")
		self.assertTrue(field, "the farm has nowhere to map groups to an event")
		self.assertEqual(field.fieldtype, "Table")
		self.assertEqual(field.options, "Livestock Event Item Group")

	def test_a_row_names_an_event_type_and_an_item_group(self):
		meta = frappe.get_meta("Livestock Event Item Group")
		self.assertTrue(meta.istable)
		event = meta.get_field("event_type")
		group = meta.get_field("item_group")
		self.assertEqual((event.fieldtype, event.options), ("Link", "Livestock Event Type"))
		self.assertEqual((group.fieldtype, group.options), ("Link", "Item Group"))
		self.assertTrue(event.reqd and group.reqd, "half a mapping maps nothing")

	def test_the_settings_page_offers_it_as_an_editable_list(self):
		"""The generic settings editor renders every Table field; this checks the
		page actually gets it, not merely that the DocType has it."""
		from upande_livestock.serverscripts.settings.livestock_settings import (
			livestock_settings,
		)

		tables = {t["fieldname"] for t in livestock_settings()["tables"]}
		self.assertIn("custom_event_item_groups", tables)


from unittest.mock import patch

from upande_livestock.serverscripts.common import event_items as EI


class TestWhichGroupsAnEventDrawsOn(unittest.TestCase):
	ROWS = [
		{"event_type": "Calving", "item_group": "Dairy Drugs"},
		{"event_type": "Calving", "item_group": "Dairy Others"},
		{"event_type": "Calving", "item_group": "Dairy Drugs"},
		{"event_type": "Vaccination", "item_group": "Dairy Drugs"},
	]

	def test_an_event_draws_on_every_group_mapped_to_it(self):
		with patch.object(EI, "_mapping_rows", return_value=self.ROWS):
			self.assertEqual(
				EI.groups_for_event("Calving"), ["Dairy Drugs", "Dairy Others"]
			)

	def test_a_group_mapped_twice_is_listed_once(self):
		"""Two rows naming the same group is a typo, not a doubling."""
		with patch.object(EI, "_mapping_rows", return_value=self.ROWS):
			self.assertEqual(EI.groups_for_event("Calving").count("Dairy Drugs"), 1)

	def test_an_event_with_no_rows_draws_on_nothing(self):
		with patch.object(EI, "_mapping_rows", return_value=self.ROWS):
			self.assertEqual(EI.groups_for_event("Heat Detection"), [])
			self.assertFalse(EI.consumes_items("Heat Detection"))
			self.assertTrue(EI.consumes_items("Vaccination"))


class TestWhereTheItemsComeFrom(unittest.TestCase):
	"""Every warehouse of the event's company, and no other company's.

	The configured store list is gone. It was what accidentally kept another
	company's stock off a Karen Roses event — there are 761 leaf warehouses
	across six companies on this bench — so company scoping is now the only
	guard, and an unscoped search would offer a drug ERPNext then refuses.
	"""

	BALANCES = [
		# same item in two stores of the same company
		{"name": "DRUG-A", "item_name": "Alamyan Spray", "stock_uom": "CAN",
		 "warehouse": "Westwood Dairy Store - KR", "qty": 4.0},
		{"name": "DRUG-A", "item_name": "Alamyan Spray", "stock_uom": "CAN",
		 "warehouse": "General Store Karen - KR", "qty": 16.0},
		{"name": "DRUG-B", "item_name": "Sutures", "stock_uom": "Piece(s)",
		 "warehouse": "Westwood Dairy Store - KR", "qty": 10.0},
	]

	def _items(self):
		with patch.object(EI, "groups_for_event", return_value=["Dairy Drugs"]), \
		     patch.object(EI, "_company_warehouses",
		                  return_value=["Westwood Dairy Store - KR", "General Store Karen - KR"]), \
		     patch.object(EI, "_balances", return_value=self.BALANCES):
			return EI.items_for_event("Vaccination", company="Karen Roses")

	def test_one_choice_per_item_not_per_shelf(self):
		self.assertEqual(len(self._items()), 2)

	def test_the_choice_names_the_store_holding_the_most(self):
		a = next(i for i in self._items() if i["value"] == "DRUG-A")
		self.assertEqual(a["warehouse"], "General Store Karen - KR")
		self.assertEqual(a["qty"], 16.0)
		self.assertIn("16 CAN in General Store Karen - KR", a["label"])

	def test_it_lists_every_store_holding_any_most_first(self):
		a = next(i for i in self._items() if i["value"] == "DRUG-A")
		self.assertEqual(
			[l["warehouse"] for l in a["locations"]],
			["General Store Karen - KR", "Westwood Dairy Store - KR"],
		)

	def test_balances_are_never_summed_across_stores(self):
		"""16 here and 4 there is not 20 anywhere, and an issue drawn on 20
		would fail at the shelf."""
		a = next(i for i in self._items() if i["value"] == "DRUG-A")
		self.assertEqual(a["qty"], 16.0)

	def test_an_event_with_no_groups_offers_nothing(self):
		with patch.object(EI, "groups_for_event", return_value=[]), \
		     patch.object(EI, "_company_warehouses") as wh, \
		     patch.object(EI, "_balances") as bal:
			self.assertEqual(EI.items_for_event("Heat Detection", company="Karen Roses"), [])
			wh.assert_not_called()
			bal.assert_not_called()

	def test_no_company_and_no_default_offers_nothing(self):
		with patch.object(EI, "groups_for_event", return_value=["Dairy Drugs"]), \
		     patch.object(EI, "_default_company", return_value=None), \
		     patch.object(EI, "_balances") as bal:
			self.assertEqual(EI.items_for_event("Vaccination"), [])
			bal.assert_not_called()

	def test_the_default_company_is_used_when_none_is_given(self):
		with patch.object(EI, "groups_for_event", return_value=["Dairy Drugs"]), \
		     patch.object(EI, "_default_company", return_value="Karen Roses"), \
		     patch.object(EI, "_company_warehouses", return_value=["W - KR"]) as wh, \
		     patch.object(EI, "_balances", return_value=[]):
			EI.items_for_event("Vaccination")
			wh.assert_called_once_with("Karen Roses")

	def test_default_company_reads_the_setting(self):
		with patch.object(frappe.db, "get_single_value", return_value="Karen Roses") as g:
			self.assertEqual(EI._default_company(), "Karen Roses")
			g.assert_called_once_with("Livestock Settings", "custom_default_company")
		with patch.object(frappe.db, "get_single_value", side_effect=Exception("x")):
			self.assertIsNone(EI._default_company())

	def test_only_the_companys_warehouses_are_searched(self):
		seen = {}

		def fake_balances(groups, warehouses):
			seen["warehouses"] = warehouses
			return []

		with patch.object(EI, "groups_for_event", return_value=["Dairy Drugs"]), \
		     patch.object(EI, "_company_warehouses", return_value=["Westwood Dairy Store - KR"]), \
		     patch.object(EI, "_balances", side_effect=fake_balances):
			EI.items_for_event("Vaccination", company="Karen Roses")
		self.assertEqual(seen["warehouses"], ["Westwood Dairy Store - KR"])



class TestMappingFallsBackBeforeMigrate(unittest.TestCase):
	"""A deploy that lands before its migrate must not take event forms down."""

	def test_a_settings_meta_without_the_table_gives_nothing(self):
		meta = type("M", (), {"has_field": lambda self, f: False})()
		with patch.object(frappe, "get_meta", return_value=meta), \
		     patch.object(frappe, "get_all") as ga:
			self.assertEqual(EI._mapping_rows(), [])
			ga.assert_not_called()

	def test_a_failing_query_gives_nothing(self):
		with patch.object(frappe, "get_all", side_effect=Exception("no table")):
			self.assertEqual(EI._mapping_rows(), [])

	def test_the_real_query_runs_with_the_right_filters(self):
		if not frappe.get_meta("Livestock Settings").has_field("custom_event_item_groups"):
			self.skipTest("this site has not migrated the mapping table yet")
		outcome = {}
		original = frappe.get_all

		def real_get_all(*args, **kwargs):
			# _mapping_rows swallows errors, so record whether the real call worked.
			try:
				outcome["rows"] = original(*args, **kwargs)
			except Exception as e:
				outcome["error"] = e
				raise
			return outcome["rows"]

		with patch.object(frappe, "get_all", side_effect=real_get_all) as ga:
			EI._mapping_rows()
		ga.assert_called_once()
		self.assertNotIn("error", outcome)
		self.assertIsInstance(outcome["rows"], list)
		kwargs = ga.call_args.kwargs
		self.assertEqual(kwargs["filters"], {"parenttype": "Livestock Settings", "parentfield": "custom_event_item_groups"})
		self.assertEqual(kwargs["order_by"], "idx asc")


def _companies_with_leaf_warehouses():
	return frappe.get_all(
		"Warehouse", filters={"is_group": 0, "disabled": 0}, distinct=True, pluck="company"
	)


class TestTheRealQueries(unittest.TestCase):
	"""Unmocked: column names, filters and IN-list expansion against the DB."""

	def _company(self):
		companies = _companies_with_leaf_warehouses()
		if not companies:
			raise unittest.SkipTest("no company has a leaf warehouse on this site")
		return companies[0]

	def test_company_warehouses_are_leaf_enabled_and_the_companys_own(self):
		company = self._company()
		names = EI._company_warehouses(company)
		self.assertTrue(names)
		for n in names[:25]:
			co, grp, dis = frappe.db.get_value("Warehouse", n, ["company", "is_group", "disabled"])
			self.assertEqual((co, grp, dis), (company, 0, 0))

	def test_company_warehouses_excludes_group_and_disabled_ones(self):
		company = self._company()
		names = set(EI._company_warehouses(company))
		excluded = frappe.get_all(
			"Warehouse",
			filters={"company": company},
			or_filters={"is_group": 1, "disabled": 1},
			pluck="name",
		)
		self.assertFalse(names & set(excluded))

	def test_no_company_gives_no_warehouses(self):
		self.assertEqual(EI._company_warehouses(None), [])

	def test_two_companies_do_not_share_warehouses(self):
		companies = [c for c in _companies_with_leaf_warehouses() if c]
		if len(companies) < 2:
			raise unittest.SkipTest("fewer than two companies have leaf warehouses on this site")
		a = set(EI._company_warehouses(companies[0]))
		b = set(EI._company_warehouses(companies[1]))
		self.assertTrue(a and b)
		self.assertFalse(a & b)

	def test_balances_executes_and_returns_the_keys_callers_use(self):
		row = frappe.db.sql(
			"""SELECT i.item_group, b.warehouse FROM `tabBin` b
			   JOIN `tabItem` i ON i.name = b.item_code
			   WHERE b.actual_qty > 0 AND IFNULL(i.disabled, 0) = 0
			     AND IFNULL(i.is_stock_item, 1) = 1 LIMIT 1""",
			as_dict=True,
		)
		if not row:
			self.skipTest("no stocked item on this site")
		rows = EI._balances([row[0].item_group], [row[0].warehouse])
		self.assertTrue(rows)
		for key in ("name", "item_name", "stock_uom", "warehouse", "qty"):
			self.assertIn(key, rows[0])
		self.assertEqual({r["warehouse"] for r in rows}, {row[0].warehouse})

	def test_balances_with_nothing_to_search_returns_nothing(self):
		self.assertEqual(EI._balances([], ["x"]), [])
		self.assertEqual(EI._balances(["x"], []), [])
