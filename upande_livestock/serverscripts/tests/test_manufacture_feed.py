# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The System feeding path can now accept a chosen recipe.

`manufacture_feed` (desk) and `record_feeding`'s `manufacture` action (mobile)
both reach `_engine.manufacture_herd_feed(bom_no=...)`. Before this, neither
endpoint read `bom_no` off its payload at all — a recipe picker offering "run
this previously-used recipe unchanged" on the System tab had no way to get the
choice there, and the client worked around the gap by routing through
`manual_feed` instead, which hardcodes `feed_mode="Manual"`. That mislabels a
System run as Manual and corrupts the System/Manual split the Rations page
reports on.

The fix threads `bom_no` through both endpoints, validated by
`_tuned_bom._base_for` — the same check `manual_feed`'s `tuned_bom` already
uses to decide whether a `base_bom` belongs to a herd — so nothing here can
drift from that rule. `bom_no` omitted must behave exactly as before: the
herd's own standing ration, labelled System.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding._engine import get_herd_feeding_program
from upande_livestock.serverscripts.feeding._tuned_bom import tuned_bom
from upande_livestock.serverscripts.feeding.manufacture_feed import manufacture_feed
from upande_livestock.serverscripts.mobile.record_feeding import record_feeding


def _a_feedable_herd():
	for row in frappe.get_all("Herds", fields=["name", "bom", "number_of_animals"]):
		if row.bom and (row.number_of_animals or 0) > 0:
			if get_herd_feeding_program(row.name)["can_manufacture"]:
				return row.name
	return None


def _a_feedable_herd_with_a_different_standing_bom(herd, standing_bom):
	for row in frappe.get_all("Herds", fields=["name", "bom", "number_of_animals"]):
		if row.name == herd or row.bom == standing_bom:
			continue
		if row.bom and (row.number_of_animals or 0) > 0:
			if get_herd_feeding_program(row.name)["can_manufacture"]:
				return row.name
	return None


class TestManufactureFeedBomNo(IntegrationTestCase):
	def setUp(self):
		self.herd = _a_feedable_herd()
		if not self.herd:
			self.skipTest("no herd on kaitet.local can currently be fed")
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not self.employee:
			self.skipTest("no active Employee on this site")
		self.standing_bom = frappe.db.get_value("Herds", self.herd, "bom")
		base = frappe.get_doc("BOM", self.standing_bom)
		lines = [{"item_code": row.item_code, "qty": flt(row.qty)} for row in base.items]
		lines[0]["qty"] = flt(lines[0]["qty"]) + 3
		# A "previously-used recipe" for this herd — a submitted, non-default
		# BOM whose custom_herd is this herd. Exactly what the picker offers
		# back for a System run of a recipe used before.
		self.recipe = tuned_bom(self.herd, lines)
		self.assertNotEqual(self.recipe, self.standing_bom, "the tune must differ from the standing BOM")

	def tearDown(self):
		frappe.db.rollback()

	def test_an_explicit_bom_no_is_used_and_stays_labelled_system(self):
		res = manufacture_feed(self.herd, employee=self.employee, bom_no=self.recipe)
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(res["bom_no"], self.recipe)
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.custom_feed_mode, "System")

	def test_omitting_bom_no_is_unchanged(self):
		res = manufacture_feed(self.herd, employee=self.employee)
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(res["bom_no"], self.standing_bom)
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.custom_feed_mode, "System")

	def test_a_bom_no_for_another_herd_is_refused(self):
		other = _a_feedable_herd_with_a_different_standing_bom(self.herd, self.standing_bom)
		if not other:
			self.skipTest("no second feedable herd with a distinct standing BOM on kaitet.local")
		other_standing = frappe.db.get_value("Herds", other, "bom")
		other_base = frappe.get_doc("BOM", other_standing)
		other_lines = [
			{"item_code": row.item_code, "qty": flt(row.qty)} for row in other_base.items
		]
		other_lines[0]["qty"] = flt(other_lines[0]["qty"]) + 5
		other_recipe = tuned_bom(other, other_lines)

		res = manufacture_feed(self.herd, employee=self.employee, bom_no=other_recipe)
		self.assertIn("error", res)

	def test_a_bom_no_for_the_wrong_item_is_refused(self):
		wrong_item_bom = frappe.db.get_value(
			"BOM",
			{"item": ["!=", frappe.db.get_value("BOM", self.standing_bom, "item")], "docstatus": 1},
			"name",
		)
		if not wrong_item_bom:
			self.skipTest("no submitted BOM on kaitet.local is for a different item")
		res = manufacture_feed(self.herd, employee=self.employee, bom_no=wrong_item_bom)
		self.assertIn("error", res)

	def test_the_mobile_manufacture_action_passes_bom_no_through(self):
		res = record_feeding(
			{
				"action": "manufacture",
				"herd": self.herd,
				"employee": self.employee,
				"bom_no": self.recipe,
			}
		)
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(res["bom_no"], self.recipe)
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.custom_feed_mode, "System")


class TestManufactureFeedSharedStandingBom(IntegrationTestCase):
	"""2-4 and STEAMERS each hold a standing BOM that is shared with, and
	`custom_herd`-attributed to, their partner herd. A validation that only
	checked `custom_herd == herd` would refuse them their own standing
	ration — this proves it does not."""

	def _run(self, herd):
		bom_name = frappe.db.get_value("Herds", herd, "bom")
		if not bom_name:
			self.skipTest(f"{herd} has no BOM on this site")
		if not get_herd_feeding_program(herd)["can_manufacture"]:
			self.skipTest(f"{herd} cannot currently be fed on this site")
		employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not employee:
			self.skipTest("no active Employee on this site")
		res = manufacture_feed(herd, employee=employee, bom_no=bom_name)
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(res["bom_no"], bom_name)
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.custom_feed_mode, "System")
		frappe.db.rollback()

	def test_2_4_can_run_its_own_shared_standing_ration(self):
		self._run("2-4")

	def test_steamers_can_run_its_own_shared_standing_ration(self):
		self._run("STEAMERS")
