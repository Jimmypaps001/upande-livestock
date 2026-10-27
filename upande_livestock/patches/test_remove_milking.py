# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The beef app has no milking. The patch removes what a dairy install left."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches import remove_milking


class TestRemoveMilking(IntegrationTestCase):
	def test_patch_is_noop_on_clean_site(self):
		remove_milking.execute()
		remove_milking.execute()

	def test_removes_milking_artifacts(self):
		if not frappe.db.exists("Stock Entry Type", "Milking"):
			frappe.get_doc({"doctype": "Stock Entry Type", "name": "Milking", "purpose": "Material Receipt"}).insert(
				ignore_permissions=True
			)
		field = "Stock Entry-custom_cows_milked"
		if not frappe.db.exists("Custom Field", field):
			frappe.get_doc(
				{
					"doctype": "Custom Field",
					"dt": "Stock Entry",
					"fieldname": "custom_cows_milked",
					"fieldtype": "Int",
					"label": "Cows Milked",
				}
			).insert(ignore_permissions=True)

		remove_milking.execute()

		self.assertFalse(frappe.db.exists("Stock Entry Type", "Milking"))
		self.assertFalse(frappe.db.exists("Custom Field", field))
		self.assertFalse(frappe.db.exists("Role", "Livestock Milker"))
		self.assertFalse(frappe.db.exists("DocType", "Milk Recording"))
		self.assertFalse(frappe.db.exists("DocType", "Livestock Milking Herd"))

	def test_refuses_with_submitted_milk_data(self):
		if not frappe.db.table_exists("Milk Recording"):
			self.skipTest("no Milk Recording table on this site")
		count = frappe.db.sql("select count(*) from `tabMilk Recording` where docstatus = 1")[0][0]
		if not count:
			self.skipTest("no submitted Milk Recording to refuse on")
		with self.assertRaises(frappe.ValidationError) as ctx:
			remove_milking.execute()
		self.assertIn(str(count), str(ctx.exception))
