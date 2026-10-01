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
		), unittest.mock.patch("frappe.db.get_value", return_value=0):
			self.assertFalse(_shared._type_consumes_drugs("Calving"))


EI = "upande_livestock.serverscripts.common.event_items.items_for_event"
OLD = "upande_livestock.serverscripts.common.stock_items.stock_items"


class TestTheEndpointsReallyCallTheMapping(unittest.TestCase):
	def _call(self, fn):
		with unittest.mock.patch(EI, return_value=[]) as new, unittest.mock.patch(OLD, return_value=[]) as old:
			fn()
		return new, old

	def test_open_health_cases_asks_for_treatment(self):
		from upande_livestock.serverscripts.health.open_health_cases import open_health_cases

		# The endpoint binds the name at import, so patch it where it is used.
		with unittest.mock.patch(
			"upande_livestock.serverscripts.health.open_health_cases.items_for_event", return_value=[]
		) as new, unittest.mock.patch(OLD, return_value=[]) as old:
			open_health_cases()
		new.assert_any_call("Treatment")
		old.assert_not_called()

	def test_husbandry_options_and_drugs_in_store_ask_the_mapping(self):
		from upande_livestock.serverscripts.husbandry.drugs_in_store import drugs_in_store
		from upande_livestock.serverscripts.husbandry.husbandry_options import husbandry_options

		for fn in (husbandry_options, drugs_in_store):
			new, old = self._call(fn)
			self.assertTrue(new.called, fn.__name__)
			old.assert_not_called()

	def test_drug_consuming_types_follow_the_mapping(self):
		from upande_livestock.serverscripts.husbandry import husbandry_options as ho

		with unittest.mock.patch.object(ho, "_type_consumes_drugs", side_effect=lambda t: t == "Dehorning"):
			self.assertEqual(ho.husbandry_options()["drug_consuming_types"], ["Dehorning"])


class TestHusbandryDrugItems(unittest.TestCase):
	def test_an_item_in_two_types_is_listed_once_with_its_fullest_store(self):
		from upande_livestock.serverscripts.husbandry import _shared

		def fake(event_type, company=None):
			wh = "Big Store" if event_type == "Vaccination" else "Small Store"
			return [{"value": "X", "item_name": "X", "warehouse": wh}]

		with unittest.mock.patch(EI, side_effect=fake):
			out = _shared.husbandry_drug_items()
		self.assertEqual(len(out), 1)
		self.assertEqual(out[0]["warehouse"], "Big Store")  # first type's choice survives


class TestForeignItemsAreRefused(unittest.TestCase):
	GROUPS = "upande_livestock.serverscripts.common.event_items.groups_for_event"

	def test_an_item_from_another_types_group_is_refused_by_name(self):
		from upande_livestock.serverscripts.husbandry import _shared

		with unittest.mock.patch(self.GROUPS, return_value=["Vaccines"]), unittest.mock.patch(
			"frappe.db.get_value", return_value="Dewormers"
		):
			with self.assertRaises(frappe.ValidationError) as cm:
				_shared._refuse_foreign_items("Vaccination", [{"item_code": "WORMEX"}])
		self.assertIn("WORMEX", str(cm.exception))
		self.assertIn("Vaccination", str(cm.exception))

	def test_an_item_in_the_types_own_group_passes(self):
		from upande_livestock.serverscripts.husbandry import _shared

		with unittest.mock.patch(self.GROUPS, return_value=["Vaccines"]), unittest.mock.patch(
			"frappe.db.get_value", return_value="Vaccines"
		):
			_shared._refuse_foreign_items("Vaccination", [{"item_code": "FMD"}])
