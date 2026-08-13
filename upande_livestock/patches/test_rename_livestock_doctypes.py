# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.rename_livestock_doctypes import RENAMES, execute


class TestRenameLivestockDoctypes(IntegrationTestCase):
	def test_renames_cover_nine_pairs(self):
		self.assertEqual(len(RENAMES), 9)
		for old, new in RENAMES:
			self.assertTrue(old.startswith("Animal "))
			self.assertTrue(new.startswith("Livestock "))

	def test_longest_name_first(self):
		lengths = [len(old) for old, _ in RENAMES]
		self.assertEqual(lengths, sorted(lengths, reverse=True))

	def test_all_new_doctypes_exist_after_patch(self):
		execute()
		for _old, new in RENAMES:
			self.assertTrue(frappe.db.exists("DocType", new), f"{new} missing")

	def test_patch_is_idempotent(self):
		execute()
		execute()
		for _old, new in RENAMES:
			self.assertTrue(frappe.db.exists("DocType", new))
