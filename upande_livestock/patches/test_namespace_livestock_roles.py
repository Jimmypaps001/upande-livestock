# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The roles the module owns, and the reach it gave up.

The point of this patch is narrowing. Before it, four roles could read, write,
create, delete, submit and cancel across all sixteen doctypes, and roughly 390
people held one — against four who had ever used the module. The tests that matter
are therefore about what each role *cannot* do, not what it can.

Two are load-bearing beyond that:

* the grant must survive a user whose existing links are broken. `yammah@` points
  at a Role Profile that no longer exists and four roles that were deleted; a patch
  that re-saves the User fails on that unrelated rot, which is why the child row is
  inserted directly.
* `Milking Palour Checksheet` must be gone. This patch narrowed it to System
  Manager; it has since been dropped from the app outright, so the assertion is
  now that no such DocType survives migrate at all.
"""

import os

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.namespace_livestock_roles import (
	ASSIGNMENTS,
	NEW_ROLES,
	execute,
)


def _roles_on(doctype):
	return {p.role for p in frappe.get_meta(doctype).permissions}


class TestNamespaceLivestockRoles(IntegrationTestCase):
	def test_every_role_exists_after_the_patch(self):
		execute()
		for role in NEW_ROLES:
			self.assertTrue(frappe.db.exists("Role", role), f"{role} was not created")

	def test_livestock_manager_is_adopted_not_recreated(self):
		"""It pre-dates the patch and the app already used it in sixteen permission
		blocks, so recreating it would orphan its holders."""
		self.assertNotIn("Livestock Manager", NEW_ROLES)
		self.assertTrue(frappe.db.exists("Role", "Livestock Manager"))

	def test_running_twice_changes_nothing(self):
		execute()
		before = frappe.db.count("Has Role", {"parenttype": "User"})
		execute()
		self.assertEqual(frappe.db.count("Has Role", {"parenttype": "User"}), before)

	def test_the_general_roles_no_longer_reach_livestock(self):
		"""The whole point: Farm Manager (130 holders) and Agriculture User (267)
		could read and write every animal. Neither is a livestock job."""
		for doctype in ("Animal", "Herds", "Livestock Event", "Milk Recording"):
			roles = _roles_on(doctype)
			for stale in ("Farm Manager", "Agriculture User", "Agriculture Manager",
			              "Dairy Secretary", "HOD Dairy", "Dairy Supervisor"):
				self.assertNotIn(stale, roles, f"{stale} still reaches {doctype}")

	def test_the_retired_checksheet_is_gone(self):
		"""This patch narrowed it to System Manager; it has since been dropped.

		The files are deleted, so `remove_orphan_doctypes()` clears the DocType
		record on the next migrate — non-destructively, leaving
		`tabMilking Palour Checksheet` and its rows in place on purpose. The
		assertion is therefore about what the app ships, not what the site holds.
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

	def test_each_role_is_confined_to_its_job(self):
		"""A milker cannot treat a cow; a vet cannot dispose of one."""
		self.assertNotIn("Livestock Milker", _roles_on("Livestock Health Case"))
		self.assertNotIn("Livestock Vet", _roles_on("Livestock Disposal"))
		self.assertNotIn("Livestock Attendant", _roles_on("Livestock Diagnosis"))
		self.assertNotIn("Livestock Breeder", _roles_on("Milk Recording"))

	def test_disposal_is_management_only(self):
		self.assertEqual(
			_roles_on("Livestock Disposal"), {"System Manager", "Livestock Manager"}
		)

	def test_every_role_can_still_see_the_animal_it_works_on(self):
		"""Confinement must not go so far that the job becomes impossible."""
		animal = _roles_on("Animal")
		for role in NEW_ROLES:
			self.assertIn(role, animal, f"{role} cannot see an Animal")

	def test_the_milker_can_record_milk_and_the_attendant_can_only_read_it(self):
		perms = {p.role: p for p in frappe.get_meta("Milk Recording").permissions}
		self.assertTrue(perms["Livestock Milker"].create)
		self.assertTrue(perms["Livestock Attendant"].read)
		self.assertFalse(perms["Livestock Attendant"].create)

	def test_a_user_with_broken_links_can_still_be_granted(self):
		"""Re-saving a User revalidates every link it already carries. Several here
		are dead — a Role Profile and four roles that no longer exist — so a
		save-based grant fails on rot that has nothing to do with this patch."""
		user = next(iter(ASSIGNMENTS))
		if not frappe.db.exists("User", user):
			self.skipTest(f"{user} is not on this site")
		execute()
		for role in ASSIGNMENTS[user]:
			self.assertTrue(
				frappe.db.exists(
					"Has Role", {"parent": user, "role": role, "parenttype": "User"}
				),
				f"{user} did not receive {role}",
			)

	def test_assignments_name_roles_that_exist(self):
		for user, roles in ASSIGNMENTS.items():
			for role in roles:
				self.assertTrue(frappe.db.exists("Role", role), f"{user} -> missing {role}")
