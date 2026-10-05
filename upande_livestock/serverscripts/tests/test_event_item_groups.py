"""Which item groups an event type may consume, as a list of any length.

`stock_items` knew exactly two kinds, "drug" and "semen", each resolving to one
item group through a constant in the source. A Calving that uses gloves,
lubricant, a bolus and an antiseptic had nowhere to say so, and the farm could
not add one without a deploy.

The list is unbounded: an event type may draw on no groups, one, four or seven.
It lives on the Livestock Event Type itself (Posts Stock Entry, Item Groups,
Default Store, Must Name an Item) — it replaced a Settings table of one row per
(event, group). `_mapping_rows` still hands callers the (event, group) pairs.
"""

import unittest

import frappe


class TestTheRuleLivesOnTheEventType(unittest.TestCase):
	def test_the_event_type_carries_the_rule_fields(self):
		meta = frappe.get_meta("Livestock Event Type")
		expected = {
			"posts_stock_entry": ("Check", None),
			"stock_item_groups": ("Table MultiSelect", "Livestock Event Type Item Group"),
			"default_store": ("Link", "Warehouse"),
			"must_name_item": ("Check", None),
		}
		for fieldname, (fieldtype, options) in expected.items():
			field = meta.get_field(fieldname)
			self.assertTrue(field, f"Livestock Event Type has no {fieldname}")
			self.assertEqual(field.fieldtype, fieldtype, fieldname)
			if options:
				self.assertEqual(field.options, options, fieldname)

	def test_a_group_row_names_an_item_group(self):
		meta = frappe.get_meta("Livestock Event Type Item Group")
		self.assertTrue(meta.istable)
		group = meta.get_field("item_group")
		self.assertEqual((group.fieldtype, group.options), ("Link", "Item Group"))

	def test_the_settings_no_longer_carry_the_old_table(self):
		"""One source of truth: the Settings table it replaced is gone."""
		meta = frappe.get_meta("Livestock Settings")
		for gone in ("custom_event_item_groups", "custom_drug_item_group",
		             "custom_semen_item_group", "custom_drug_warehouses",
		             "drug_warehouse", "semen_warehouse"):
			self.assertFalse(meta.has_field(gone), gone)


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

	def test_an_event_type_meta_without_the_rule_gives_nothing(self):
		meta = type("M", (), {"has_field": lambda self, f: False})()
		with patch.object(frappe, "get_meta", return_value=meta), \
		     patch.object(frappe, "get_all") as ga:
			self.assertEqual(EI._rules(), {})
			self.assertEqual(EI._mapping_rows(), [])
			ga.assert_not_called()

	def test_a_failing_query_gives_nothing(self):
		with patch.object(frappe, "get_all", side_effect=Exception("no table")):
			self.assertEqual(EI._rules(), {})
			self.assertEqual(EI._mapping_rows(), [])

	def test_the_real_queries_run_with_the_right_filters(self):
		outcome = {"errors": []}
		original = frappe.get_all

		def real_get_all(*args, **kwargs):
			# _rules swallows errors, so record whether the real calls worked.
			try:
				return original(*args, **kwargs)
			except Exception as e:
				outcome["errors"].append(e)
				raise

		with patch.object(frappe, "get_all", side_effect=real_get_all) as ga:
			rules = EI._rules()
		self.assertEqual(outcome["errors"], [])
		self.assertIsInstance(rules, dict)
		# Only the two rule queries (get_meta may itself call get_all on a cold cache).
		ours = [c for c in ga.call_args_list
		        if c.args and c.args[0] in ("Livestock Event Type", "Livestock Event Type Item Group")]
		self.assertEqual(len(ours), 2)
		types_call, groups_call = ours
		self.assertEqual(types_call.args[0], "Livestock Event Type")
		self.assertEqual(types_call.kwargs["filters"], {"posts_stock_entry": 1})
		self.assertEqual(groups_call.args[0], "Livestock Event Type Item Group")
		self.assertEqual(
			groups_call.kwargs["filters"],
			{"parenttype": "Livestock Event Type", "parentfield": "stock_item_groups"},
		)
		self.assertEqual(groups_call.kwargs["order_by"], "idx asc")


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
