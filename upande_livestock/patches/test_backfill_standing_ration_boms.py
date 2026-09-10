# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.backfill_standing_ration_boms import execute

FIELDS = ["custom_herd", "custom_is_livestock_feed", "custom_ration_kind"]
# custom_is_livestock_feed (Check) is a NOT NULL column; None only works for
# the Link and Select fields.
BLANK = {"custom_herd": None, "custom_is_livestock_feed": 0, "custom_ration_kind": ""}


class TestBackfillStandingRationBoms(IntegrationTestCase):
	def _reset(self, bom_name):
		"""Blank the three fields on `bom_name` and remember their original
		values so tearDown can put them back — this patch commits, so a plain
		rollback will not undo it."""
		original = frappe.db.get_value("BOM", bom_name, FIELDS, as_dict=True)
		self.addCleanup(self._restore, bom_name, original)
		for fieldname, blank in BLANK.items():
			frappe.db.set_value("BOM", bom_name, fieldname, blank, update_modified=False)
		frappe.db.commit()

	def _restore(self, bom_name, original):
		for fieldname in FIELDS:
			value = original.get(fieldname)
			if value is None and fieldname in BLANK:
				value = BLANK[fieldname]
			frappe.db.set_value("BOM", bom_name, fieldname, value, update_modified=False)
		frappe.db.commit()

	def _a_solo_herd(self):
		"""A herd whose BOM only that one herd points at."""
		counts = {}
		for row in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"]):
			counts.setdefault(row.bom, []).append(row.name)
		for bom_name, herds in counts.items():
			if len(herds) == 1:
				return herds[0], bom_name
		raise AssertionError("kaitet.local has no herd whose standing BOM is unshared")

	def _a_shared_bom(self):
		counts = {}
		for row in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"]):
			counts.setdefault(row.bom, []).append(row.name)
		for bom_name, herds in counts.items():
			if len(herds) > 1:
				return bom_name, herds
		raise AssertionError("kaitet.local has no BOM shared by two herds")

	def test_a_solo_herds_bom_is_stamped_standing_with_the_herd(self):
		herd, bom_name = self._a_solo_herd()
		self._reset(bom_name)

		execute()

		got = frappe.db.get_value("BOM", bom_name, FIELDS, as_dict=True)
		self.assertEqual(got.custom_herd, herd)
		self.assertEqual(got.custom_is_livestock_feed, 1)
		self.assertEqual(got.custom_ration_kind, "Standing")

	def test_a_bom_shared_by_two_herds_is_stamped_but_not_linked_to_either(self):
		"""A single custom_herd cannot hold two herds. Left blank rather than
		guessed — see the module docstring for why."""
		bom_name, herds = self._a_shared_bom()
		self.assertEqual(len(herds), 2)
		self._reset(bom_name)

		execute()

		got = frappe.db.get_value("BOM", bom_name, FIELDS, as_dict=True)
		self.assertFalse(got.custom_herd)
		self.assertEqual(got.custom_is_livestock_feed, 1)
		self.assertEqual(got.custom_ration_kind, "Standing")

	def test_the_herds_own_bom_link_is_untouched(self):
		"""The backfill only stamps the BOM side; it must not repoint
		Herds.bom or Item.default_bom."""
		herd, bom_name = self._a_solo_herd()
		before_herd_bom = frappe.db.get_value("Herds", herd, "bom")
		before_item = frappe.db.get_value("BOM", bom_name, "item")
		before_default_bom = frappe.db.get_value("Item", before_item, "default_bom")
		self._reset(bom_name)

		execute()

		self.assertEqual(frappe.db.get_value("Herds", herd, "bom"), before_herd_bom)
		self.assertEqual(frappe.db.get_value("Item", before_item, "default_bom"), before_default_bom)

	def test_the_backfill_is_idempotent(self):
		herd, bom_name = self._a_solo_herd()
		self._reset(bom_name)

		execute()
		execute()

		got = frappe.db.get_value("BOM", bom_name, FIELDS, as_dict=True)
		self.assertEqual(got.custom_herd, herd)
		self.assertEqual(got.custom_is_livestock_feed, 1)
		self.assertEqual(got.custom_ration_kind, "Standing")
