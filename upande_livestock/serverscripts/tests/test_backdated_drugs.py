import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, flt, today

from upande_livestock.serverscripts.common import event_items
from upande_livestock.serverscripts.husbandry.create_husbandry_event import create_husbandry_event


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _bin_qty(item, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty"))


class TestBackdatedDrugs(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(_set_window, 0)
		_set_window(1)
		# The Deworming type's default store, and an item in a group it draws on.
		self.warehouse = event_items.default_store("Deworming")
		groups = event_items.groups_for_event("Deworming")
		row = self.warehouse and groups and frappe.db.sql(
			"""SELECT b.item_code FROM `tabBin` b JOIN `tabItem` i ON i.name = b.item_code
			   WHERE b.warehouse = %s AND b.actual_qty > 10 AND i.item_group IN %s LIMIT 1""",
			(self.warehouse, groups),
			as_dict=True,
		)
		if not row:
			self.skipTest("no drug stock on kaitet.local to test against")
		self.item = row[0].item_code
		tag = frappe.generate_hash(length=10)
		self.animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": tag,
				"burn_name": tag,
				"sex": "Female",
				"status": "Active",
				"date_of_birth": add_months(today(), -30),
			}
		).insert(ignore_permissions=True)
		self.operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		self.addCleanup(frappe.db.rollback)

	def _deworm(self, event_date):
		return create_husbandry_event(
			{
				"event_type": "Deworming",
				"animal": self.animal.name,
				"event_date": event_date,
				"operator": self.operator,
				"drugs": [
					{"item_code": self.item, "qty": 2, "source_warehouse": self.warehouse}
				],
			}
		)

	def test_a_backdated_treatment_leaves_the_store_alone(self):
		before = _bin_qty(self.item, self.warehouse)
		res = self._deworm(add_days(today(), -40))
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(_bin_qty(self.item, self.warehouse), before)

	def test_a_backdated_treatment_posts_no_stock_entry(self):
		res = self._deworm(add_days(today(), -40))
		self.assertEqual(res.get("stock_entry"), "")
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertFalse(event.stock_entry)

	def test_the_drug_rows_survive_for_the_reconciliation(self):
		"""The quantities are the whole point — dropping them would make the
		later reconciliation pass impossible."""
		res = self._deworm(add_days(today(), -40))
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertEqual(len(event.drug_issues), 1)
		self.assertEqual(event.drug_issues[0].item_code, self.item)
		self.assertEqual(flt(event.drug_issues[0].qty), 2.0)

	def test_the_event_is_flagged_for_the_reconciliation(self):
		res = self._deworm(add_days(today(), -40))
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertEqual(event.custom_unposted_drugs, 1)
		self.assertEqual(event.custom_is_backdated, 1)

	def test_a_live_treatment_still_issues(self):
		"""The suppression must not leak into today's work."""
		before = _bin_qty(self.item, self.warehouse)
		res = self._deworm(today())
		self.assertNotIn("error", res, res.get("error"))
		self.assertTrue(res.get("stock_entry"))
		self.assertEqual(_bin_qty(self.item, self.warehouse), before - 2)
