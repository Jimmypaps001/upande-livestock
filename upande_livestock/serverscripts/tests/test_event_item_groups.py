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
		with patch.object(EI, "groups_for_event", return_value=[]):
			self.assertEqual(EI.items_for_event("Heat Detection", company="Karen Roses"), [])

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
