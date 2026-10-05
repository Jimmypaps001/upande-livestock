"""Finding a drug: which item group, which stores, and where each one is.

The drug picker was empty on the live site, for two reasons either of which
was enough on its own.

ONE, the item group was a constant. `stock_items` asked for item_group
"DRUGS" because that is what this developer's database calls it — 606 items
here. Live calls its drug catalogue `Dairy Drugs` (215 items). A farm names
its own item groups and the code has no business knowing them. The groups now
come from each Livestock Event Type's stock rule.

TWO, the store was a single setting pointing somewhere empty.
`Livestock Settings.drug_warehouse` named `Livestock Drug Store - KR`, a
warehouse with **zero Bin rows** on live, while the drugs were spread over the
stores the farm actually uses. The configured store list and the single
setting are gone: the picker searches every leaf warehouse of the company and
SAYS WHERE each drug is. The event type's Default Store, when it holds the
drug, is offered first.

`stock_items` and the drug/semen group and store settings were removed; these
tests now cover `event_items.items_for_event`, which replaced them.
"""

import importlib
import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import event_items as EI
from upande_livestock.serverscripts.common import stock as ST


class TestTheItemGroupIsTheFarmsToName(unittest.TestCase):
	def test_the_group_comes_from_the_event_types_rule(self):
		rules = {"Vaccination": {"posts": True, "groups": ["Dairy Drugs"], "default_store": None, "must_name_item": False}}
		with patch.object(EI, "_rules", return_value=rules):
			self.assertEqual(EI.groups_for_event("Vaccination"), ["Dairy Drugs"])
			self.assertEqual(EI.groups_for_event("Service"), [])

	def test_the_old_constants_and_settings_are_gone(self):
		with self.assertRaises(ImportError):
			importlib.import_module("upande_livestock.serverscripts.common.stock_items")
		meta = frappe.get_meta("Livestock Settings")
		for gone in ("custom_drug_item_group", "custom_semen_item_group"):
			self.assertFalse(meta.has_field(gone), gone)


class TestWhichStoresAreSearched(unittest.TestCase):
	def test_the_configured_store_list_is_gone(self):
		for gone in ("drug_warehouse", "semen_warehouse", "drug_source_warehouses", "_drug_warehouse_rows"):
			self.assertFalse(hasattr(ST, gone), gone)
		meta = frappe.get_meta("Livestock Settings")
		for gone in ("custom_drug_warehouses", "drug_warehouse", "semen_warehouse"):
			self.assertFalse(meta.has_field(gone), gone)

	def test_every_leaf_warehouse_of_the_company_is_searched(self):
		seen = {}

		def spy(groups, warehouses):
			seen["warehouses"] = warehouses
			return []

		with patch.object(EI, "groups_for_event", return_value=["Dairy Drugs"]), \
		     patch.object(EI, "_company_warehouses", return_value=["A - KR", "B - KR"]) as cw, \
		     patch.object(EI, "_balances", side_effect=spy):
			EI.items_for_event("Vaccination", company="Karen Roses")
		cw.assert_called_once_with("Karen Roses")
		self.assertEqual(seen["warehouses"], ["A - KR", "B - KR"])


class TestEachDrugSaysWhereItIs(unittest.TestCase):
	"""What `feed_in_store` already promises, for drugs."""

	ROWS = [
		frappe._dict(name="D1", item_name="Oxytet", stock_uom="Litre", qty=40, warehouse="Clinic Store - KR"),
		frappe._dict(name="D1", item_name="Oxytet", stock_uom="Litre", qty=5, warehouse="Delivery Truck - KR"),
		frappe._dict(name="D2", item_name="Betamox", stock_uom="Vial", qty=3, warehouse="Delivery Truck - KR"),
	]

	def _items(self, default_store=None):
		with patch.object(EI, "groups_for_event", return_value=["Dairy Drugs"]), \
		     patch.object(EI, "_company_warehouses", return_value=["Clinic Store - KR", "Delivery Truck - KR"]), \
		     patch.object(EI, "default_store", return_value=default_store), \
		     patch.object(EI, "_balances", return_value=self.ROWS):
			return {i["value"]: i for i in EI.items_for_event("Vaccination", company="Karen Roses")}

	def test_each_choice_names_a_warehouse(self):
		self.assertEqual(self._items()["D1"]["warehouse"], "Clinic Store - KR")

	def test_the_warehouse_named_is_the_one_holding_the_most(self):
		"""So the issue draws from a store that can actually supply it, rather
		than from a shelf that happens to be first alphabetically."""
		self.assertEqual(self._items()["D2"]["warehouse"], "Delivery Truck - KR")

	def test_the_quantity_is_the_one_in_that_warehouse(self):
		"""Never the sum: a summed balance offers stock the issue cannot find."""
		self.assertEqual(self._items()["D1"]["qty"], 40)

	def test_every_store_holding_it_is_listed(self):
		self.assertEqual(
			self._items()["D1"]["locations"],
			[
				{"warehouse": "Clinic Store - KR", "qty": 40},
				{"warehouse": "Delivery Truck - KR", "qty": 5},
			],
		)

	def test_the_event_types_default_store_comes_first_when_it_holds_the_drug(self):
		d1 = self._items(default_store="Delivery Truck - KR")["D1"]
		self.assertEqual(d1["warehouse"], "Delivery Truck - KR")
		self.assertEqual(d1["qty"], 5)
		self.assertEqual([l["warehouse"] for l in d1["locations"]], ["Delivery Truck - KR", "Clinic Store - KR"])

	def test_the_label_says_where_to_go_and_get_it(self):
		label = self._items()["D1"]["label"]
		self.assertIn("Oxytet", label)
		self.assertIn("40", label)
		self.assertIn("Clinic Store - KR", label)

	def test_one_choice_per_item_not_per_shelf(self):
		"""The picker picks a drug; the warehouse rides along with it."""
		self.assertEqual(sorted(self._items()), ["D1", "D2"])
