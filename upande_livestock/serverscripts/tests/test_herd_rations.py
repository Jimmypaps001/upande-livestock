# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Making a herd, and deciding what it eats.

Two things the farm asked for and could not do: split a herd off the animals it
already has, and revise a ration without a developer.

The judgement underneath both: A CHANGED RECIPE SUPERSEDES, IT DOES NOT EDIT. A
submitted BOM seals — ERPNext answers an edit with "Not allowed to change Qty
after submission" — so there is nowhere to put new numbers anyway. That turns
out to be what you want: every feed run ever posted points at the BOM it was
mixed from, and rewriting that in place would silently restate what the farm
fed last March.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding.set_herd_ration import set_herd_ration
from upande_livestock.serverscripts.herds.create_herd import create_herd
from upande_livestock.serverscripts.tests.test_culling import _employee, _tidy
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge

HERD = "ZZ TEST SPLIT HERD"
RATION_ITEM = "Lactating Group 2"
COWS = ["RATION-TEST-1", "RATION-TEST-2"]


def _lines(*pairs):
	return [{"item_code": code, "qty": qty} for code, qty in pairs]


#: Real feed items on this site, in the units the formulations are written in.
SILAGE, HAY, MINERAL = "4040010082", "4040010034", "4040010052"


def _drop_herd():
	frappe.set_user("Administrator")
	for animal in COWS:
		_tidy(animal)
	if frappe.db.exists("Herds", HERD):
		bom = frappe.db.get_value("Herds", HERD, "bom")
		for name in frappe.get_all("BOM", filters={"custom_herd": HERD}, pluck="name"):
			frappe.db.set_value("BOM", name, {"is_default": 0, "custom_herd": None},
			                    update_modified=False)
			try:
				doc = frappe.get_doc("BOM", name)
				if doc.docstatus == 1:
					doc.cancel()
				frappe.delete_doc("BOM", name, force=True, ignore_permissions=True)
			except Exception:
				frappe.clear_last_message()
		if bom:
			frappe.db.set_value("Herds", HERD, "bom", None)
		_purge("Herds", HERD)
	frappe.db.commit()


class TestSplittingAHerdOffTheAnimalsYouHave(IntegrationTestCase):
	def setUp(self):
		_drop_herd()
		for tag in COWS:
			_make_cow(tag, herd="Lactating group 1")
		frappe.db.commit()
		self.addCleanup(_drop_herd)

	def test_the_animals_arrive_and_the_counts_follow(self):
		before = frappe.db.get_value("Herds", "Lactating group 1", "number_of_animals")
		got = create_herd({"herd_name": HERD, "animals": COWS, "operator": _employee()})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["heads"], len(COWS))
		self.assertEqual(
			frappe.db.get_value("Herds", "Lactating group 1", "number_of_animals"),
			before - len(COWS),
		)

	def test_every_animal_arrives_by_a_movement_event(self):
		"""Her timeline has to be able to say where she was in March, and who
		moved her. A direct write to current_herd leaves a herd full of animals
		nobody ever saw arrive."""
		create_herd({"herd_name": HERD, "animals": COWS, "operator": _employee()})
		for tag in COWS:
			self.assertTrue(frappe.db.exists("Livestock Event", {
				"animal": tag, "event_type": "Movement", "new_herd": HERD, "docstatus": 1}))

	def test_a_herd_can_be_made_with_no_animals_at_all(self):
		"""A pen you are about to fill is still a pen."""
		got = create_herd({"herd_name": HERD, "animals": []})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["heads"], 0)

	def test_a_name_already_taken_is_refused(self):
		create_herd({"herd_name": HERD, "animals": [], "operator": _employee()})
		again = create_herd({"herd_name": HERD, "animals": []})
		self.assertIn("already a herd", again.get("error", ""))

	def test_an_animal_that_has_left_the_farm_cannot_join_one(self):
		frappe.db.set_value("Animal", COWS[0], {"disabled": 1, "status": "Sold"})
		got = create_herd({"herd_name": HERD, "animals": COWS, "operator": _employee()})
		self.assertIn("left the farm", got.get("error", ""))
		self.assertFalse(frappe.db.exists("Herds", HERD))

	def test_every_problem_with_the_selection_is_named_at_once(self):
		"""Thirty cows off a list, four problems — say all four."""
		got = create_herd({"herd_name": HERD,
		                   "animals": [*COWS, "NO-SUCH-ANIMAL", COWS[0]]})
		self.assertIn("NO-SUCH-ANIMAL", got.get("error", ""))
		self.assertIn("twice", got.get("error", ""))

	def test_a_herd_can_be_born_with_its_ration(self):
		got = create_herd({
			"herd_name": HERD, "animals": COWS, "operator": _employee(),
			"ration_item": RATION_ITEM,
			"lines": _lines((SILAGE, 20.0), (HAY, 2.0), (MINERAL, 0.15)),
		})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["ration"]["per_head_kg"], 22.15)
		self.assertEqual(frappe.db.get_value("Herds", HERD, "bom"), got["ration"]["bom"])


class TestRevisingWhatAHerdIsFed(IntegrationTestCase):
	def setUp(self):
		_drop_herd()
		for tag in COWS:
			_make_cow(tag, herd="Lactating group 1")
		create_herd({"herd_name": HERD, "animals": COWS, "operator": _employee(),
		             "ration_item": RATION_ITEM,
		             "lines": _lines((SILAGE, 20.0), (HAY, 2.0))})
		frappe.db.commit()
		self.first = frappe.db.get_value("Herds", HERD, "bom")
		self.addCleanup(_drop_herd)

	def test_the_output_is_the_sum_of_the_lines(self):
		"""The one invariant the live site's own rations break."""
		self.assertEqual(flt(frappe.db.get_value("BOM", self.first, "quantity")), 22.0)

	def test_saving_the_same_ration_twice_mints_nothing(self):
		"""A farm correcting the same way every morning must not accumulate a
		BOM a day — which is what this site's BOM list already looks like."""
		got = set_herd_ration({"herd": HERD, "lines": _lines((SILAGE, 20.0), (HAY, 2.0))})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertFalse(got["changed"])
		self.assertEqual(got["bom"], self.first)
		self.assertEqual(got["differences"], [])

	def test_a_changed_ration_supersedes_rather_than_edits(self):
		got = set_herd_ration({"herd": HERD, "lines": _lines((SILAGE, 23.0), (HAY, 2.0))})
		self.assertTrue(got["changed"])
		self.assertNotEqual(got["bom"], self.first)
		self.assertEqual(got["superseded"], self.first)
		self.assertEqual(frappe.db.get_value("Herds", HERD, "bom"), got["bom"])

	def test_the_old_revision_stays_readable(self):
		"""Every feed run ever posted points at the BOM it was mixed from."""
		set_herd_ration({"herd": HERD, "lines": _lines((SILAGE, 23.0), (HAY, 2.0))})
		self.assertEqual(frappe.db.get_value("BOM", self.first, "docstatus"), 1)
		rows = frappe.get_all("BOM Item", filters={"parent": self.first},
		                      fields=["item_code", "qty"])
		self.assertEqual({r.item_code: flt(r.qty) for r in rows}, {SILAGE: 20.0, HAY: 2.0})

	def test_it_says_what_actually_changed(self):
		got = set_herd_ration({
			"herd": HERD,
			"lines": _lines((SILAGE, 23.0), (MINERAL, 0.15)),
		})
		what = {d["item_code"]: d["what"] for d in got["differences"]}
		self.assertEqual(what, {SILAGE: "raised", HAY: "dropped", MINERAL: "added"})

	def test_reverting_lands_back_on_the_recipe_it_had(self):
		"""A ration changed and changed back is the same ration, not a third copy."""
		set_herd_ration({"herd": HERD, "lines": _lines((SILAGE, 23.0), (HAY, 2.0))})
		back = set_herd_ration({"herd": HERD, "lines": _lines((SILAGE, 20.0), (HAY, 2.0))})
		self.assertEqual(back["bom"], self.first)

	def test_the_herd_and_the_item_agree_on_which_bom_is_current(self):
		"""BOM.is_default and Item.default_bom are two halves of one fact."""
		got = set_herd_ration({"herd": HERD, "lines": _lines((SILAGE, 23.0), (HAY, 2.0))})
		self.assertEqual(frappe.db.get_value("Item", RATION_ITEM, "default_bom"), got["bom"])
		self.assertEqual(frappe.db.get_value("BOM", got["bom"], "is_default"), 1)

	def test_the_days_requirement_follows_the_ration(self):
		"""The number that decides what leaves the store in the morning."""
		got = set_herd_ration({"herd": HERD, "lines": _lines((SILAGE, 30.0), (HAY, 2.0))})
		self.assertEqual(got["per_head_kg"], 32.0)
		self.assertEqual(got["day_kg"], 32.0 * len(COWS))

	def test_an_empty_ration_is_refused(self):
		got = set_herd_ration({"herd": HERD, "lines": []})
		self.assertIn("at least one ingredient", got.get("error", ""))

	def test_a_ration_for_a_herd_that_is_not_there_is_refused(self):
		got = set_herd_ration({"herd": "NO SUCH HERD", "lines": _lines((SILAGE, 1.0))})
		self.assertIn("not a herd", got.get("error", ""))
