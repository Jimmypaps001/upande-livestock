# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Do the roles actually work? Asked by impersonation, not by reading JSON.

Checking the permission rows says what was *written*. It does not say what a person
holding that role can do, which is the only question that matters — Frappe resolves
access through role membership, permlevels, `if_owner`, user permissions and the
doctype's own rules, and a row can be right while the outcome is wrong.

So each test signs in as a user holding exactly one role and asks
`frappe.has_permission`. The negative cases carry the weight: the whole point of the
change was that a milker could previously delete an animal and a vet could dispose
of the herd, because four roles held everything across all sixteen doctypes.
"""

import os

import frappe
from frappe.tests import IntegrationTestCase

ROLE_USERS = {
	"Livestock Vet": "_test_lsk_vet@example.com",
	"Livestock Breeder": "_test_lsk_breeder@example.com",
	"Livestock Attendant": "_test_lsk_attendant@example.com",
	"Livestock Milker": "_test_lsk_milker@example.com",
	"Livestock Stores": "_test_lsk_stores@example.com",
	"Livestock Manager": "_test_lsk_manager@example.com",
}


class TestLivestockRolePermissions(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for role, email in ROLE_USERS.items():
			if not frappe.db.exists("Role", role):
				frappe.get_doc(
					{"doctype": "Role", "role_name": role, "desk_access": 1}
				).insert(ignore_permissions=True)
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": role,
					"send_welcome_email": 0,
					# Exactly one livestock role, so the result is attributable.
					"roles": [{"role": role}],
				}
			)
			user.flags.ignore_permissions = True
			user.insert()
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for email in ROLE_USERS.values():
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def _can(self, role, doctype, ptype="create"):
		"""True if a user holding only `role` may do `ptype` on `doctype`."""
		frappe.set_user(ROLE_USERS[role])
		try:
			return bool(frappe.has_permission(doctype, ptype))
		finally:
			frappe.set_user("Administrator")

	# ---------------------------------------------------------------- each job

	def test_the_vet_treats_and_nothing_else(self):
		self.assertTrue(self._can("Livestock Vet", "Livestock Health Case"))
		self.assertTrue(self._can("Livestock Vet", "Livestock Diagnosis"))
		self.assertFalse(self._can("Livestock Vet", "Livestock Disposal"))
		self.assertFalse(self._can("Livestock Vet", "Milk Recording"))

	def test_the_milker_records_milk_and_nothing_else(self):
		self.assertTrue(self._can("Livestock Milker", "Milk Recording"))
		self.assertFalse(self._can("Livestock Milker", "Livestock Health Case"))
		self.assertFalse(self._can("Livestock Milker", "Livestock Disposal"))
		self.assertFalse(self._can("Livestock Milker", "Livestock Event"))

	def test_the_breeder_works_reproduction(self):
		self.assertTrue(self._can("Livestock Breeder", "Livestock Event"))
		self.assertTrue(self._can("Livestock Breeder", "Calf Rearing"))
		self.assertFalse(self._can("Livestock Breeder", "Milk Recording"))
		self.assertFalse(self._can("Livestock Breeder", "Livestock Disposal"))

	def test_the_attendant_moves_and_feeds(self):
		self.assertTrue(self._can("Livestock Attendant", "Livestock Event"))
		self.assertTrue(self._can("Livestock Attendant", "Livestock Weight Record"))
		self.assertFalse(self._can("Livestock Attendant", "Livestock Diagnosis"))
		self.assertFalse(self._can("Livestock Attendant", "Livestock Disposal"))

	def test_the_attendant_can_read_milk_but_not_record_it(self):
		self.assertTrue(self._can("Livestock Attendant", "Milk Recording", "read"))
		self.assertFalse(self._can("Livestock Attendant", "Milk Recording", "create"))

	def test_disposal_is_management_only(self):
		self.assertTrue(self._can("Livestock Manager", "Livestock Disposal"))
		for role in ("Livestock Vet", "Livestock Breeder", "Livestock Attendant",
		             "Livestock Milker", "Livestock Stores"):
			self.assertFalse(
				self._can(role, "Livestock Disposal"), f"{role} can dispose of an animal"
			)

	def test_every_role_can_see_the_animal_it_works_on(self):
		"""Confinement must not make the job impossible."""
		for role in ROLE_USERS:
			self.assertTrue(self._can(role, "Animal", "read"), f"{role} cannot see an Animal")

	def test_no_field_role_can_delete_an_animal(self):
		"""Previously every livestock role could. Deleting a cow is not a field task."""
		for role in ("Livestock Vet", "Livestock Breeder", "Livestock Attendant",
		             "Livestock Milker", "Livestock Stores"):
			self.assertFalse(
				self._can(role, "Animal", "delete"), f"{role} can delete an Animal"
			)

	def test_the_app_no_longer_ships_the_retired_checksheet(self):
		"""It was narrowed to System Manager, then dropped from the app outright.

		Asserted against the filesystem, not against `tabDocType`: the site's
		DocType record is cleared by `remove_orphan_doctypes()` on the next
		migrate, so checking the database would fail on any site that has not
		migrated yet and pass for the wrong reason on one that has. What this
		app controls — and what a future commit could regress — is whether the
		schema file ships at all. (The directory itself can linger on an existing
		bench as a stale `__pycache__`, so the JSON is the honest signal.)
		"""
		self.assertFalse(
			os.path.exists(
				frappe.get_app_path(
					"upande_livestock",
					"upande_livestock",
					"doctype",
					"milking_palour_checksheet",
					"milking_palour_checksheet.json",
				)
			),
			"the retired checksheet is back in the app",
		)

	def test_settings_are_management_only(self):
		self.assertTrue(self._can("Livestock Manager", "Livestock Settings", "write"))
		for role in ("Livestock Vet", "Livestock Milker", "Livestock Attendant"):
			self.assertFalse(self._can(role, "Livestock Settings", "write"))
