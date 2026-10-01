"""Every picker asks the mapping, and the configured store lists are retired.

The drug picker searched `drug_source_warehouses()` — a list somebody typed —
and on live that list was empty while `drug_warehouse` named a store with zero
stocked bins, so it returned 0 drugs on three screens while 74 stocked drug
bins sat elsewhere. The item already knows where it is.
"""

import inspect
import unittest
import unittest.mock

import frappe


class TestNoPickerStillAsksTheOldWay(unittest.TestCase):
	MODULES = (
		"upande_livestock.serverscripts.husbandry.husbandry_options",
		"upande_livestock.serverscripts.health.open_health_cases",
		"upande_livestock.serverscripts.husbandry.drugs_in_store",
	)

	def test_none_of_them_calls_stock_items(self):
		for name in self.MODULES:
			mod = __import__(name, fromlist=["x"])
			src = inspect.getsource(mod)
			self.assertNotIn(
				"stock_items(", src,
				f"{name} still asks the two-kind lookup rather than the mapping",
			)

	def test_none_of_them_reads_a_configured_store_list(self):
		for name in self.MODULES:
			mod = __import__(name, fromlist=["x"])
			src = inspect.getsource(mod)
			self.assertNotIn("drug_source_warehouses", src, f"{name} still reads the store list")


class TestWhetherATypeConsumes(unittest.TestCase):
	def test_it_is_the_mapping_that_decides_now(self):
		from upande_livestock.serverscripts.husbandry import _shared

		with unittest.mock.patch(
			"upande_livestock.serverscripts.common.event_items.groups_for_event",
			return_value=["Dairy Drugs"],
		):
			self.assertTrue(_shared._type_consumes_drugs("Calving"))
		with unittest.mock.patch(
			"upande_livestock.serverscripts.common.event_items.groups_for_event",
			return_value=[],
		):
			self.assertFalse(_shared._type_consumes_drugs("Calving"))
