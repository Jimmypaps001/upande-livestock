# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The beef app has no milking. The patch removes what a dairy install left."""

from unittest.mock import patch

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

	def test_refuses_with_submitted_milk_recordings(self):
		with patch.object(remove_milking, "_submitted_milk_recordings", return_value=7), patch.object(
			remove_milking, "_submitted_milking_entries", return_value=0
		):
			with self.assertRaises(frappe.ValidationError) as ctx:
				remove_milking.execute()
		self.assertIn("7 submitted Milk Recording", str(ctx.exception))

	def test_refuses_with_submitted_milking_stock_entries(self):
		with patch.object(remove_milking, "_submitted_milk_recordings", return_value=0), patch.object(
			remove_milking, "_submitted_milking_entries", return_value=3
		):
			with self.assertRaises(frappe.ValidationError) as ctx:
				remove_milking.execute()
		self.assertIn("3 submitted Stock Entry", str(ctx.exception))

	def test_the_milking_entry_count_reads_submitted_entries_of_that_type(self):
		with patch.object(frappe.db, "exists", return_value=True), patch.object(
			frappe.db, "count", return_value=5
		) as count:
			self.assertEqual(remove_milking._submitted_milking_entries(), 5)
		count.assert_called_once_with("Stock Entry", {"stock_entry_type": "Milking", "docstatus": 1})

	def test_the_recording_count_reads_submitted_rows(self):
		with patch.object(frappe.db, "table_exists", return_value=True), patch.object(
			frappe.db, "sql", return_value=[(4,)]
		):
			self.assertEqual(remove_milking._submitted_milk_recordings(), 4)

	def test_the_kept_calf_field_is_never_a_removal_target(self):
		names = {f for _dt, f in remove_milking._milk_custom_fields()}
		self.assertNotIn("custom_milk_feeding_pct_of_body_weight", names)
