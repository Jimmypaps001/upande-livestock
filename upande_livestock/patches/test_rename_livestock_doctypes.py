# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

import upande_livestock.patches.rename_livestock_doctypes as rename_patch
from upande_livestock.patches.rename_livestock_doctypes import RENAMES, execute


def make_throwaway_doctype(name):
	"""Create a genuine, disposable custom DocType with a couple of fields.

	Used to drive execute() against real DocType/table/document machinery
	without ever touching the nine production Animal*/Livestock* doctypes.
	"""
	doc = frappe.get_doc(
		{
			"doctype": "DocType",
			"name": name,
			"module": "Upande Livestock",
			"custom": 1,
			"fields": [
				{"fieldname": "title", "fieldtype": "Data", "label": "Title"},
				{"fieldname": "value", "fieldtype": "Int", "label": "Value"},
			],
			"permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def drop_doctype_if_exists(name):
	"""Remove a throwaway DocType's meta record and its underlying table.

	frappe.delete_doc("DocType", ...) only removes the meta rows (a plain DML
	delete) and never drops the doctype's own data table, so both are handled
	explicitly here. The meta delete is also just DML — unlike the CREATE/DROP
	TABLE statements, which are DDL and auto-commit — so an explicit commit is
	needed or a later per-test rollback can resurrect the meta row for a table
	that no longer exists, breaking the next test run.
	"""
	if frappe.db.exists("DocType", name):
		frappe.delete_doc("DocType", name, force=True, ignore_permissions=True)
	if frappe.db.table_exists(name):
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{name}`")
	frappe.db.commit()
	frappe.clear_cache()


class TestRenameLivestockDoctypes(IntegrationTestCase):
	def test_renames_cover_nine_pairs(self):
		self.assertEqual(len(RENAMES), 9)
		for old, new in RENAMES:
			self.assertTrue(old.startswith("Animal "))
			self.assertTrue(new.startswith("Livestock "))

	def test_longest_name_first(self):
		lengths = [len(old) for old, _ in RENAMES]
		self.assertEqual(lengths, sorted(lengths, reverse=True))

	def test_execute_renames_table_and_preserves_data(self):
		old, new = "ZZ Rename Test Old", "ZZ Rename Test New"
		self.addCleanup(drop_doctype_if_exists, old)
		self.addCleanup(drop_doctype_if_exists, new)

		make_throwaway_doctype(old)
		row = frappe.get_doc({"doctype": old, "title": "before rename", "value": 42}).insert(
			ignore_permissions=True
		)
		row_name = row.name

		original_renames = rename_patch.RENAMES
		rename_patch.RENAMES = [(old, new)]
		self.addCleanup(setattr, rename_patch, "RENAMES", original_renames)

		execute()

		self.assertFalse(frappe.db.exists("DocType", old), f"{old} should be gone after execute()")
		self.assertTrue(frappe.db.exists("DocType", new), f"{new} missing after execute()")
		self.assertFalse(frappe.db.table_exists(old), f"old table for {old} should be gone")
		self.assertTrue(frappe.db.table_exists(new), f"new table for {new} should exist")
		self.assertEqual(
			frappe.db.get_value(new, row_name, ["title", "value"], as_dict=True),
			{"title": "before rename", "value": 42},
		)

	def test_execute_is_idempotent(self):
		old, new = "ZZ Rename Test Idempotent Old", "ZZ Rename Test Idempotent New"
		self.addCleanup(drop_doctype_if_exists, old)
		self.addCleanup(drop_doctype_if_exists, new)

		make_throwaway_doctype(old)
		row = frappe.get_doc({"doctype": old, "title": "idempotent", "value": 7}).insert(
			ignore_permissions=True
		)
		row_name = row.name

		original_renames = rename_patch.RENAMES
		rename_patch.RENAMES = [(old, new)]
		self.addCleanup(setattr, rename_patch, "RENAMES", original_renames)

		execute()
		execute()  # old no longer exists on the second pass -> skipped cleanly

		self.assertTrue(frappe.db.exists("DocType", new))
		self.assertFalse(frappe.db.exists("DocType", old))
		self.assertEqual(frappe.db.get_value(new, row_name, "value"), 7)

	def test_execute_raises_on_conflict_and_touches_neither_side(self):
		old, new = "ZZ Rename Test Conflict Old", "ZZ Rename Test Conflict New"
		self.addCleanup(drop_doctype_if_exists, old)
		self.addCleanup(drop_doctype_if_exists, new)

		make_throwaway_doctype(old)
		make_throwaway_doctype(new)

		original_renames = rename_patch.RENAMES
		rename_patch.RENAMES = [(old, new)]
		self.addCleanup(setattr, rename_patch, "RENAMES", original_renames)

		self.assertRaises(frappe.ValidationError, execute)

		# The conflict must abort loudly, not silently drop one side.
		self.assertTrue(frappe.db.exists("DocType", old))
		self.assertTrue(frappe.db.exists("DocType", new))
