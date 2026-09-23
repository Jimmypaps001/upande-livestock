"""Finding a drug: which item group, which stores, and where each one is.

The drug picker was empty on the live site, for two reasons either of which
was enough on its own.

ONE, the item group was a constant. `stock_items` asked for item_group
"DRUGS" because that is what this developer's database calls it — 606 items
here. Live calls its drug catalogue `Dairy Drugs` (215 items); its `Drugs`
group is a near-empty parent node with 12. `DAIRY`, which the semen lookup
asks for, has no items on live at all, so that picker was dead too. A farm
names its own item groups and the code has no business knowing them.

TWO, the store was a single setting pointing somewhere empty.
`Livestock Settings.drug_warehouse` is `Livestock Drug Store - KR`, a
warehouse created 2026-08-26 with **zero Bin rows** — no stock has ever moved
through it. The drugs are spread over the stores the farm actually uses:
Drug/Medicine Store - Old Office (18 items), Westwood Dairy Store (16),
General Store Karen (10), Delivery Truck (9), Clinic Store (1). Feeding solved
this shape of problem already, with an ordered list of source warehouses, and
drugs get the same.

So the picker searches every configured drug store and SAYS WHERE each drug
is, rather than promising stock from one shelf that may hold none of it. That
is the same promise `feed_in_store` makes, and it is what makes the issue
draw from a store that can actually supply it.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import \
        test_drug_store_lookup as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import stock as ST
from upande_livestock.serverscripts.common import stock_items as SI


class TestTheItemGroupIsTheFarmsToName(unittest.TestCase):
	def test_the_drug_group_comes_from_the_setting(self):
		with patch.object(frappe.db, "get_single_value", return_value="Dairy Drugs"):
			self.assertEqual(SI.item_group_for("drug"), "Dairy Drugs")

	def test_the_semen_group_comes_from_its_own_setting(self):
		with patch.object(frappe.db, "get_single_value", return_value="Dairy Semen"):
			self.assertEqual(SI.item_group_for("semen"), "Dairy Semen")

	def test_an_unset_setting_keeps_the_old_constant(self):
		"""kaitet.local's groups really are DRUGS and DAIRY, and a site that
		has not filled the setting in must keep working exactly as before."""
		with patch.object(frappe.db, "get_single_value", return_value=None):
			self.assertEqual(SI.item_group_for("drug"), "DRUGS")
			self.assertEqual(SI.item_group_for("semen"), "DAIRY")

	def test_the_settings_carry_both_fields(self):
		meta = frappe.get_meta("Livestock Settings")
		self.assertTrue(meta.has_field("custom_drug_item_group"))
		self.assertTrue(meta.has_field("custom_semen_item_group"))
		self.assertEqual(meta.get_field("custom_drug_item_group").options, "Item Group")


class TestWhichStoresAreSearched(unittest.TestCase):
	def test_the_configured_rows_come_first_in_grid_order(self):
		rows = [
			frappe._dict(warehouse="Drug/Medicine Store - Old Office - KR"),
			frappe._dict(warehouse="Clinic Store - KR"),
		]
		with patch.object(ST, "_drug_warehouse_rows", return_value=rows), patch.object(
			ST, "drug_warehouse", return_value=None
		):
			self.assertEqual(
				ST.drug_source_warehouses(),
				["Drug/Medicine Store - Old Office - KR", "Clinic Store - KR"],
			)

	def test_the_single_setting_is_still_searched_last(self):
		"""A site that configures nothing keeps the behaviour it had."""
		with patch.object(ST, "_drug_warehouse_rows", return_value=[]), patch.object(
			ST, "drug_warehouse", return_value="Livestock Drug Store - KR"
		):
			self.assertEqual(ST.drug_source_warehouses(), ["Livestock Drug Store - KR"])

	def test_it_is_not_listed_twice_when_it_is_also_a_row(self):
		rows = [frappe._dict(warehouse="Clinic Store - KR")]
		with patch.object(ST, "_drug_warehouse_rows", return_value=rows), patch.object(
			ST, "drug_warehouse", return_value="Clinic Store - KR"
		):
			self.assertEqual(ST.drug_source_warehouses(), ["Clinic Store - KR"])

	def test_the_settings_carry_the_table(self):
		meta = frappe.get_meta("Livestock Settings")
		self.assertTrue(meta.has_field("custom_drug_warehouses"))
		self.assertEqual(meta.get_field("custom_drug_warehouses").fieldtype, "Table")


class TestEachDrugSaysWhereItIs(unittest.TestCase):
	"""What `feed_in_store` already promises, for drugs."""

	ROWS = [
		frappe._dict(name="D1", item_name="Oxytet", stock_uom="Litre", qty=40, warehouse="Clinic Store - KR"),
		frappe._dict(name="D1", item_name="Oxytet", stock_uom="Litre", qty=5, warehouse="Delivery Truck - KR"),
		frappe._dict(name="D2", item_name="Betamox", stock_uom="Vial", qty=3, warehouse="Delivery Truck - KR"),
	]

	def _items(self):
		with patch.object(SI, "_balances", return_value=self.ROWS):
			return {i["value"]: i for i in SI.stock_items("drug")}

	def test_each_choice_names_a_warehouse(self):
		self.assertEqual(self._items()["D1"]["warehouse"], "Clinic Store - KR")

	def test_the_warehouse_named_is_the_one_holding_the_most(self):
		"""So the issue draws from a store that can actually supply it, rather
		than from a shelf that happens to be first alphabetically."""
		self.assertEqual(self._items()["D2"]["warehouse"], "Delivery Truck - KR")

	def test_the_quantity_is_the_one_in_that_warehouse(self):
		"""Never the sum. `stock_items` has always refused to sum across
		stores, because a summed balance offers stock the issue cannot find."""
		self.assertEqual(self._items()["D1"]["qty"], 40)

	def test_every_store_holding_it_is_listed(self):
		self.assertEqual(
			self._items()["D1"]["locations"],
			[
				{"warehouse": "Clinic Store - KR", "qty": 40},
				{"warehouse": "Delivery Truck - KR", "qty": 5},
			],
		)

	def test_the_label_says_where_to_go_and_get_it(self):
		label = self._items()["D1"]["label"]
		self.assertIn("Oxytet", label)
		self.assertIn("40", label)
		self.assertIn("Clinic Store - KR", label)

	def test_one_choice_per_item_not_per_shelf(self):
		"""The picker picks a drug; the warehouse rides along with it."""
		self.assertEqual(sorted(self._items()), ["D1", "D2"])


class TestNarrowingToOneStore(unittest.TestCase):
	def test_asking_for_one_warehouse_searches_only_that_one(self):
		seen = {}

		def spy(group, warehouses, name_filter):
			seen["warehouses"] = warehouses
			return []

		with patch.object(SI, "_balances", side_effect=spy):
			SI.stock_items("drug", "Clinic Store - KR")
		self.assertEqual(seen["warehouses"], ["Clinic Store - KR"])

	def test_asking_for_none_searches_every_configured_store(self):
		seen = {}

		def spy(group, warehouses, name_filter):
			seen["warehouses"] = warehouses
			return []

		with patch.object(SI, "_balances", side_effect=spy), patch.object(
			ST, "drug_source_warehouses", return_value=["A", "B"]
		):
			SI.stock_items("drug")
		self.assertEqual(seen["warehouses"], ["A", "B"])
