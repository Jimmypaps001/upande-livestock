# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Tests for the Livestock Dashboard block's read endpoints.

Only the active-animal predicate is covered here. The dashboard and the
data-entry dropdowns must agree on what counts as active livestock, so this
asserts the dashboard honours `disabled` — the flag retire_animal() sets — and
not just the status list.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.api.test_operations import _make_cow, _purge
from upande_livestock.serverscripts.dashboard._shared import _active_animal_count
from upande_livestock.serverscripts.common.choices import is_active as _is_active


class TestActiveAnimalPredicate(IntegrationTestCase):
	def test_disabled_animal_drops_out_of_the_count(self):
		before = _active_animal_count()
		cow = _make_cow("ZZ WS ACTIVE COW")
		self.addCleanup(_purge, "Animal", cow.name)
		self.assertEqual(_active_animal_count(), before + 1)

		# Status stays Active on purpose: if the status list were still doing the
		# work on its own, this animal would keep counting.
		frappe.db.set_value("Animal", cow.name, "disabled", 1, update_modified=False)
		self.assertEqual(_active_animal_count(), before)

	def test_is_active_checks_both_predicates(self):
		self.assertTrue(_is_active({"status": "Active", "disabled": 0}))
		self.assertFalse(_is_active({"status": "Active", "disabled": 1}))
		self.assertFalse(_is_active({"status": "Sold", "disabled": 0}))
		self.assertFalse(_is_active({"status": "Dead", "disabled": 1}))
