"""Giving a herd its first ration, by naming it.

A herd that already has a TMR can have it edited. A herd that has none cannot
be given one — `_standing_ration.py` asks the herd's existing BOM what product
the ration is for, and with no existing BOM there is no answer:

    item = ration_item or (BOM.item of the herd's existing BOM)
    if not item:
        throw("Say which product this herd's ration is...")

The backend has always accepted `ration_item`. The Ration Editor has never had
a field for it and has never sent one except when copying an existing recipe,
so the throw is the only thing a farm with a new herd ever sees.

THE PART THAT IS NOT OBVIOUS: `BOM.item` is `reqd=1`. ERPNext cannot store a
recipe that is not a recipe FOR something, so "just name the ration" has to
create an Item as well as a BOM. Every livestock BOM on this site already has
one — `Lactating Group 1`, `TMR Calves Meal`, `Dry/Steamers/Incalf Heifers` —
sitting in the feed item group and named after the ration. Naming a new one
does the same, in one step, without asking: choosing the product of a recipe
you are in the middle of writing is not a decision to put in front of a farm.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import test_first_ration as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.feeding import _recipe_lines as RL
from upande_livestock.serverscripts.feeding import _standing_ration as SR


class TestNamingARationMakesTheProduct(unittest.TestCase):
	def test_a_name_that_is_not_an_item_yet_becomes_one(self):
		with patch.object(frappe.db, "exists", return_value=False), patch.object(
			SR, "_create_feed_item"
		) as made:
			made.return_value = "Fresh Calf TMR"
			self.assertEqual(SR.feed_item_for("Fresh Calf TMR"), "Fresh Calf TMR")
		made.assert_called_once_with("Fresh Calf TMR")

	def test_a_name_that_is_already_an_item_is_reused(self):
		"""Editing a ration must not mint a second product every time."""
		with patch.object(frappe.db, "exists", return_value=True), patch.object(
			SR, "_create_feed_item", side_effect=AssertionError("must not create")
		):
			self.assertEqual(SR.feed_item_for("TMR Calves Meal"), "TMR Calves Meal")

	def test_an_empty_name_is_not_a_product(self):
		self.assertIsNone(SR.feed_item_for(""))
		self.assertIsNone(SR.feed_item_for(None))
		self.assertIsNone(SR.feed_item_for("   "))

	def test_the_item_is_made_in_the_configured_feed_group(self):
		"""So the Stock page and the pickers can see it afterwards. A ration
		created into the wrong group is invisible to every page that reads
		feed, which is the bug the item-group settings exist to stop."""
		captured = {}

		class FakeDoc:
			def __init__(self, **kw):
				captured.update(kw)

			def insert(self, **kw):
				return self

			name = "Fresh Calf TMR"

		with patch.object(frappe, "get_doc", side_effect=lambda d: FakeDoc(**d)), patch(
			"upande_livestock.serverscripts.feeding.feed_in_store.feed_item_group",
			return_value="Dairy Feed",
		):
			SR._create_feed_item("Fresh Calf TMR")
		self.assertEqual(captured["item_group"], "Dairy Feed")
		self.assertEqual(captured["doctype"], "Item")
		self.assertEqual(captured["item_code"], "Fresh Calf TMR")
		self.assertTrue(captured["is_stock_item"], "a ration is stocked; it is manufactured and issued")
		self.assertEqual(captured["stock_uom"], "Kilogram", "rations are stated per kg on this farm")


class TestAHerdWithNoRationCanBeGivenOne(unittest.TestCase):
	def test_the_name_is_enough(self):
		"""No existing BOM, no chosen recipe — just a name and some lines.

		`_adopt` is stubbed along with `_build`. It is the half that WRITES —
		it points `Herds.bom` at the new recipe — and an earlier version of
		this test left it real, so a BOM name that existed only in the test was
		written onto a real herd and the next 34 tests died on
		`BOM ... not found`. A test that names a herd must never be the thing
		that repoints it.
		"""
		seen = {}

		def fake_item_for(name):
			seen["named"] = name
			return name

		with patch.object(frappe.db, "get_value", return_value=None), patch.object(
			SR, "feed_item_for", side_effect=fake_item_for
		), patch.object(SR, "_build", return_value="BOM-Fresh Calf TMR-001") as built, patch.object(
			SR, "_adopt"
		) as adopted, patch.object(SR, "_matching", return_value=None):
			SR.set_standing_ration(
				"Lactation Group 3 TEST HERD",
				[{"item_code": "Maize Germ", "qty": 2}],
				ration_item="Fresh Calf TMR",
			)
		self.assertEqual(seen["named"], "Fresh Calf TMR")
		self.assertTrue(built.called)
		adopted.assert_called_once_with("BOM-Fresh Calf TMR-001", "Lactation Group 3 TEST HERD", None)

	def test_without_a_name_it_still_refuses(self):
		"""Unchanged: a ration is a recipe FOR something and the farm names it.
		Inventing `Herd-3-ration` would put a product nobody asked for into the
		feed catalogue."""
		with patch.object(frappe.db, "get_value", return_value=None):
			with self.assertRaises(frappe.ValidationError):
				SR.set_standing_ration(
					"Lactation Group 3 TEST HERD", [{"item_code": "Maize Germ", "qty": 2}]
				)

	def test_a_ration_still_needs_an_ingredient(self):
		with self.assertRaises(frappe.ValidationError):
			SR.set_standing_ration("Lactation Group 3 TEST HERD", [], ration_item="Fresh Calf TMR")


class TestTheConcentrateLineIsMarked(unittest.TestCase):
	"""Which ingredient of a TMR is the mixed concentrate, said out loud.

	A TMR's lines are silage, hay, minerals and one line that is itself a
	manufactured mix. That last one is the only line the farm can do anything
	about on the concentrate page, and nothing on the editor said which it was —
	it had to be recognised by name.

	Concentrate-ness is not re-derived here. `feed_in_store._ration_roles`
	already decides it exactly as the engine does — a farm-mixed sub-assembly
	(`_sub_bom_for`) or an item named on Livestock Settings as bought in — so
	the editor and the feed run cannot disagree about what a concentrate is.
	"""

	def test_a_concentrate_line_is_flagged(self):
		with patch.object(RL, "_concentrate_items", return_value={"Dairy Meal 18"}), patch.object(
			frappe, "get_all", return_value=[
				frappe._dict(parent="BOM-1", item_code="Dairy Meal 18", item_name="Dairy Meal 18",
				             qty=6, uom="Kilogram", idx=1),
				frappe._dict(parent="BOM-1", item_code="Silage", item_name="Silage",
				             qty=20, uom="Kilogram", idx=2),
			]
		):
			lines = RL.lines_for(["BOM-1"])["BOM-1"]
		self.assertTrue(lines[0]["is_concentrate"])
		self.assertFalse(lines[1]["is_concentrate"])

	def test_the_flag_is_always_present(self):
		"""A missing key and a false one read the same in JavaScript, but only
		one of them survives a rename of the field."""
		with patch.object(RL, "_concentrate_items", return_value=set()), patch.object(
			frappe, "get_all", return_value=[
				frappe._dict(parent="BOM-1", item_code="Silage", item_name="Silage",
				             qty=20, uom="Kilogram", idx=1),
			]
		):
			lines = RL.lines_for(["BOM-1"])["BOM-1"]
		self.assertIn("is_concentrate", lines[0])

	def test_it_asks_the_engines_own_definition(self):
		"""Not a name match, not the item group — the same function the feed
		run uses, so the two cannot drift."""
		import inspect

		self.assertIn("_ration_roles", inspect.getsource(RL._concentrate_items))


class TestTheFeedPickerKnowsAConcentrate(unittest.TestCase):
	"""The editor's rows are editable, so the highlight cannot come from the
	saved line alone — picking a different feed has to light up or stop lighting
	up immediately. The choices carry the same flag, from the same definition."""

	def test_every_choice_says_whether_it_is_a_concentrate(self):
		from upande_livestock.serverscripts.feeding.herd_rations import herd_rations

		res = herd_rations()
		self.assertTrue(res.get("ok"), res)
		self.assertTrue(res["feeds"], "no feeds to check")
		for choice in res["feeds"]:
			self.assertIn("is_concentrate", choice)

	def test_it_is_the_same_set_the_lines_are_flagged_from(self):
		from upande_livestock.serverscripts.feeding.herd_rations import herd_rations

		with patch.object(RL, "_concentrate_items", return_value={"Maize Germ"}), patch(
			"upande_livestock.serverscripts.feeding.herd_rations._concentrate_items",
			return_value={"Maize Germ"},
		):
			res = herd_rations()
		flagged = {c["value"] for c in res["feeds"] if c["is_concentrate"]}
		self.assertEqual(flagged & {"Maize Germ"}, {"Maize Germ"} & {c["value"] for c in res["feeds"]})
