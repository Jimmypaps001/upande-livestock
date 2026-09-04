# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who may read the item master, and who may not.

The gap this closed was invisible for a long time because the people testing
the app held Stock User and Stock Manager alongside the livestock roles. A user
holding only livestock roles — which is what a farm hand holds — got "You are
not permitted to read Item" from the concentrate plan and from the drug picker.

Every livestock role now reads it, because every one of them meets a screen that
needs it — the drug picker on the husbandry, check-up and treatment screens
guards Item read just as the concentrate plan does.

So the test that matters is the other negative: reading is all they got. None of
them may write, create or delete an item, and the grant did not leak to a role
outside livestock. Seeing the item master is not having the run of it.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.grant_livestock_item_read import DOCTYPE, ROLES, execute

# A role with no livestock business must not have picked this up on the way past.
UNRELATED = ("Employee", "Blogger")


def _perm(role, right):
	"""Whether `role` has `right` on Item, from either permission table."""
	for table in ("Custom DocPerm", "DocPerm"):
		row = frappe.db.get_value(
			table, {"parent": DOCTYPE, "role": role, "permlevel": 0}, right
		)
		if row is not None:
			return bool(row)
	return False


class TestLivestockItemRead(IntegrationTestCase):
	def test_the_store_roles_may_read_the_item_master(self):
		for role in ROLES:
			if not frappe.db.exists("Role", role):
				continue
			self.assertTrue(
				_perm(role, "read"), f"{role} cannot read {DOCTYPE} — the concentrate plan is closed to it"
			)

	def test_reading_is_all_they_got(self):
		"""A store is run by seeing items, not by creating or editing them."""
		for role in ROLES:
			if not frappe.db.exists("Role", role):
				continue
			for right in ("write", "create", "delete"):
				self.assertFalse(
					_perm(role, right), f"{role} gained {right} on {DOCTYPE}, which it was never meant to have"
				)

	def test_every_livestock_role_can_read_it(self):
		"""They all meet a screen that needs it — the drug picker, or the plan."""
		for role in ROLES:
			if not frappe.db.exists("Role", role):
				continue
			self.assertTrue(_perm(role, "read"), f"{role} still cannot read {DOCTYPE}")

	def test_the_grant_did_not_leak_beyond_livestock(self):
		"""Every role this patch names starts with "Livestock"; nothing else moved."""
		for role in ROLES:
			self.assertTrue(role.startswith("Livestock"), f"{role} is not a livestock role")
		for role in UNRELATED:
			if not frappe.db.exists("Role", role):
				continue
			self.assertFalse(
				_perm(role, "read"),
				f"{role} gained read on {DOCTYPE}; this patch should not have touched it",
			)

	def test_running_twice_changes_nothing(self):
		before = {(r, p): _perm(r, p) for r in ROLES for p in ("read", "write", "create", "delete")}
		execute()
		after = {(r, p): _perm(r, p) for r in ROLES for p in ("read", "write", "create", "delete")}
		self.assertEqual(before, after)
