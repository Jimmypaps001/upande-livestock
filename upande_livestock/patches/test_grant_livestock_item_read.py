# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who may read the item master, and who may not.

The gap this closed was invisible for a long time because the people testing
the app held Stock User and Stock Manager alongside the livestock roles. A user
holding only livestock roles — which is what a farm hand holds — got "You are
not permitted to read Item" from the concentrate plan and from the drug picker.

So the test that matters is the negative one: a milker or a vet still cannot
read the item master, and the two roles that can still cannot write to it.
Granting read to run a store is not granting the run of the item master.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.grant_livestock_item_read import DOCTYPE, ROLES, execute

CANNOT_READ = ("Livestock Vet", "Livestock Milker", "Livestock Attendant", "Livestock Breeder")


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

	def test_the_other_livestock_roles_did_not_get_it(self):
		"""A vet has no reason to read the item master, and still cannot."""
		for role in CANNOT_READ:
			if not frappe.db.exists("Role", role):
				continue
			self.assertFalse(
				_perm(role, "read"), f"{role} can read {DOCTYPE}; the grant was meant to be two roles"
			)

	def test_running_twice_changes_nothing(self):
		before = {(r, p): _perm(r, p) for r in ROLES for p in ("read", "write", "create", "delete")}
		execute()
		after = {(r, p): _perm(r, p) for r in ROLES for p in ("read", "write", "create", "delete")}
		self.assertEqual(before, after)
