"""What the Concentrate page lists, weighs, and draws from.

Three corrections to what `b3913c8` shipped, all reported from the UI.

ONE DEFINITION, NOT TWO. The page listed nothing while the Ration Editor
highlighted five concentrates in the very same recipes, because they were
asking different questions:

    ration editor    _ration_roles()  — a BOM line that is itself manufactured
                     (`_sub_bom_for`) or named bought-in on Livestock Settings
    concentrate page custom_ration_kind == "Concentrate" — a field added in
                     b3913c8 that no existing BOM has ever carried

Stamping every existing BOM would have closed it for today and left the two
rules free to drift again tomorrow. So the page asks what the editor asks. The
stamp is still written on concentrates created here — it is cheap and it is
honest — but nothing reads it to decide what a concentrate is.

THE INGREDIENTS DECIDE THE TOTAL. The base was typed, on the reasoning that a
farm declares its output and moisture makes the arithmetic inexact. That
reasoning permits 5000 kg and 6000 kg of ingredients making 100 kg of meal,
which is not a recipe anybody can check against a mixer. The total is the sum of
the lines, exactly as a ration's is.

AND THE STORE IS PER INGREDIENT. One store for a whole run is the wrong grain
here: silage comes from a pit and the mineral from the drug store, and a run
that makes you pick one of them for everything is a run you cannot post.
`resolve_requirement` has always assigned a store per line via `_pick_source`;
this lets the operator override that line by line.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import test_concentrate_page as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.feeding import _concentrate as CN
from upande_livestock.serverscripts.feeding import _engine


class TestOneDefinitionOfAConcentrate(unittest.TestCase):
	def test_it_asks_what_the_ration_editor_asks(self):
		"""Not the stamp. The editor highlights on `_ration_roles`, and a page
		that decided differently is how five became zero."""
		import inspect

		self.assertIn("_ration_roles", inspect.getsource(CN.concentrate_items))

	def test_a_bom_nobody_stamped_still_lists(self):
		"""The reported bug, in one assertion: five highlighted, none listed."""
		with patch.object(CN, "concentrate_items", return_value={"Calves Meal"}):
			listed = {c["item_code"] for c in CN.concentrate_list()}
		self.assertIn("Calves Meal", listed)

	def test_the_real_site_lists_what_the_editor_highlights(self):
		from upande_livestock.serverscripts.feeding.feed_in_store import _ration_roles

		highlighted = _ration_roles()[1]
		listed = {c["item_code"] for c in CN.concentrate_list()}
		self.assertTrue(highlighted, "kaitet.local has no concentrates to check against")
		self.assertEqual(
			highlighted - listed, set(), "highlighted in the editor and missing from the page"
		)


class TestTheIngredientsDecideTheTotal(unittest.TestCase):
	LINES = [{"item_code": "Maize Germ", "qty": 300}, {"item_code": "Canola", "qty": 200}]

	def test_the_total_is_the_sum_of_the_lines(self):
		self.assertEqual(CN.total_of(self.LINES), 500)

	def test_nothing_types_a_total_any_more(self):
		"""5000 kg and 6000 kg cannot be made to produce 100 kg."""
		import inspect

		self.assertNotIn("base_qty", inspect.signature(CN.set_concentrate).parameters)

	def test_the_bom_quantity_is_that_sum(self):
		seen = {}

		def spy(item, lines, farm=None, template=None):
			seen["qty"] = CN.total_of(lines)
			return "BOM-X-001"

		with patch.object(CN, "feed_item_for", return_value="X"), patch.object(
			CN, "_build_concentrate", side_effect=spy
		), patch.object(CN, "_matching_concentrate", return_value=None), patch.object(
			CN, "_farm_for_concentrate", return_value="Kapkolia"
		):
			res = CN.set_concentrate("X", self.LINES)
		self.assertEqual(seen["qty"], 500)
		self.assertEqual(res["base_qty"], 500)

	def test_a_recipe_with_no_weight_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			CN.set_concentrate("X", [{"item_code": "Maize Germ", "qty": 0}])


class TestEachIngredientSaysWhereItIsAndHowMuch(unittest.TestCase):
	"""The same figures the Feeding page already shows, on this page too."""

	def test_a_listed_concentrate_carries_its_ingredients(self):
		with patch.object(CN, "concentrate_items", return_value={"Calves Meal"}):
			rows = CN.concentrate_list()
		row = next(r for r in rows if r["item_code"] == "Calves Meal")
		self.assertTrue(row["lines"], "no ingredients")
		for ln in row["lines"]:
			for key in ("item_code", "required_qty", "source_warehouse", "available", "short_qty"):
				self.assertIn(key, ln, f"line is missing {key}")


class TestAStorePerIngredient(unittest.TestCase):
	def test_the_run_accepts_a_store_for_each_item(self):
		import inspect

		self.assertIn("source_by_item", inspect.signature(_engine._run_manufacture).parameters)

	def test_a_named_store_overrides_only_that_line(self):
		lines = [
			{"item_code": "Silage", "source_warehouse": "Pit 1"},
			{"item_code": "Mineral", "source_warehouse": "Feed Store"},
		]
		self.assertEqual(
			_engine._source_by_item(lines, {"Silage": "Pit 2"}),
			{"Silage": "Pit 2", "Mineral": "Feed Store"},
		)

	def test_naming_nothing_keeps_what_pick_source_chose(self):
		lines = [{"item_code": "Silage", "source_warehouse": "Pit 1"}]
		self.assertEqual(_engine._source_by_item(lines, None), {"Silage": "Pit 1"})
		self.assertEqual(_engine._source_by_item(lines, {}), {"Silage": "Pit 1"})

	def test_a_blank_override_is_not_an_override(self):
		"""An untouched dropdown sends "", and that must mean "as chosen",
		not "no warehouse" — which would post the row against nothing."""
		lines = [{"item_code": "Silage", "source_warehouse": "Pit 1"}]
		self.assertEqual(_engine._source_by_item(lines, {"Silage": ""}), {"Silage": "Pit 1"})

	def test_the_concentrate_endpoint_takes_them(self):
		import inspect

		self.assertIn("source_by_item", inspect.signature(_engine.manufacture_concentrate).parameters)
