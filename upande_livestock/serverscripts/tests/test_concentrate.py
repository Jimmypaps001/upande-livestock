"""A concentrate is mixed by the kilo, and has nothing to do with cows.

The Concentrate page was driven by `concentrate_plan(days)`: demand was every
herd's per-head concentrate line × head count × days of cover, rounded up to
whole batches. That is a herd-shaped, calendar-shaped answer to a question with
neither shape. The mixer takes a tonne of ingredients and makes a tonne of
concentrate whether there are forty cows in the shed or none. Head count
belongs to the TMR, which is fed per head; it does not belong here.

So the three things the page needs are:

    create   name it, give it ingredients and say what they make
    edit     change the ingredients or the base
    mix      type the kilos

THE BASE IS NOT THE SUM OF THE LINES, which is where this parts company with a
TMR. A ration's quantity IS its per-head total — that is what a ration is. A
concentrate's ingredients are stated against an output the farm declares: 500 kg
of meal, from lines that may not add to 500 because of moisture or because the
recipe is written in round numbers. So the base is typed, and manufacturing
1000 off a 500 base consumes exactly twice the lines, which is ERPNext's own
Work Order scaling rather than arithmetic this app does.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import test_concentrate as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.feeding import _concentrate as CN


class TestMakingANewConcentrate(unittest.TestCase):
	LINES = [{"item_code": "Maize Germ", "qty": 300}, {"item_code": "Canola", "qty": 200}]

	def test_the_name_becomes_the_product(self):
		with patch.object(CN, "feed_item_for", return_value="Dairy Meal 18") as named, patch.object(
			CN, "_build_concentrate", return_value="BOM-Dairy Meal 18-001"
		), patch.object(CN, "_matching_concentrate", return_value=None):
			res = CN.set_concentrate("Dairy Meal 18", self.LINES, 500)
		named.assert_called_once_with("Dairy Meal 18")
		self.assertEqual(res["item"], "Dairy Meal 18")
		self.assertEqual(res["bom"], "BOM-Dairy Meal 18-001")
		self.assertTrue(res["changed"])

	def test_the_base_is_what_the_farm_says_it_makes(self):
		"""Not the sum of the lines. 500 kg of meal can come from lines that do
		not add to 500 — moisture, or a recipe written in round numbers."""
		seen = {}

		def spy(item, lines, base_qty, farm=None, template=None):
			seen["base"] = base_qty
			return "BOM-X-001"

		with patch.object(CN, "feed_item_for", return_value="Dairy Meal 18"), patch.object(
			CN, "_build_concentrate", side_effect=spy
		), patch.object(CN, "_matching_concentrate", return_value=None):
			CN.set_concentrate("Dairy Meal 18", self.LINES, 480)
		self.assertEqual(seen["base"], 480)

	def test_a_base_of_nothing_is_refused(self):
		for bad in (0, -1, None, ""):
			with self.assertRaises(frappe.ValidationError):
				CN.set_concentrate("Dairy Meal 18", self.LINES, bad)

	def test_it_needs_an_ingredient(self):
		with self.assertRaises(frappe.ValidationError):
			CN.set_concentrate("Dairy Meal 18", [], 500)

	def test_it_needs_a_name(self):
		with self.assertRaises(frappe.ValidationError):
			CN.set_concentrate("", self.LINES, 500)

	def test_saving_the_same_recipe_twice_mints_nothing(self):
		"""The same discipline the standing ration keeps: this site's BOM list
		is already what happens when every save makes a revision."""
		with patch.object(CN, "feed_item_for", return_value="Dairy Meal 18"), patch.object(
			CN, "_matching_concentrate", return_value="BOM-Dairy Meal 18-001"
		), patch.object(CN, "_build_concentrate", side_effect=AssertionError("must not rebuild")):
			res = CN.set_concentrate("Dairy Meal 18", self.LINES, 500)
		self.assertEqual(res["bom"], "BOM-Dairy Meal 18-001")
		self.assertFalse(res["changed"])


class TestTheBomItBuilds(unittest.TestCase):
	def test_it_is_marked_a_concentrate_and_belongs_to_no_herd(self):
		"""`custom_ration_kind` is how every page tells one BOM from another.
		A concentrate marked Standing would be offered as some herd's ration."""
		captured = {}

		class FakeBom(dict):
			def __init__(self):
				super().__init__()
				self.items = []

			def __setattr__(self, k, v):
				if k == "items":
					super().__setattr__(k, v)
				else:
					captured[k] = v

			def __getattr__(self, k):
				return captured.get(k)

			def set(self, k, v):
				captured[k] = v

			def append(self, *a, **kw):
				return {}

			def get(self, k, default=None):
				return captured.get(k, default)

			def insert(self, **kw):
				return self

			def submit(self):
				return self

			name = "BOM-Dairy Meal 18-001"
			meta = type("M", (), {"has_field": staticmethod(lambda f: False)})()

		with patch.object(frappe, "new_doc", return_value=FakeBom()), patch.object(
			frappe, "get_cached_doc", return_value=frappe._dict(item_name="Maize Germ", stock_uom="Kilogram")
		), patch.object(frappe.db, "get_single_value", return_value="Karen Roses"):
			CN._build_concentrate("Dairy Meal 18", [{"item_code": "Maize Germ", "qty": 300}], 500)

		self.assertEqual(captured["custom_ration_kind"], CN.CONCENTRATE)
		self.assertEqual(captured["quantity"], 500)
		self.assertTrue(captured["custom_is_livestock_feed"])
		self.assertIsNone(captured.get("custom_herd"), "a concentrate is mixed for the store, not a herd")


class TestMixingIsJustTheKilos(unittest.TestCase):
	def test_twice_the_base_consumes_twice_the_lines(self):
		"""ERPNext's own Work Order scaling, not arithmetic this app does."""
		from upande_livestock.serverscripts.feeding import _engine

		seen = {}

		def spy(item, bom_no, qty, what, **kw):
			seen["qty"] = qty
			seen["herd"] = kw.get("herd")
			return {"work_order": "WO-1"}

		with patch.object(_engine, "_run_manufacture", side_effect=spy), patch.object(
			frappe, "get_doc", return_value=frappe._dict(name="BOM-1", item="Dairy Meal 18", quantity=500, uom="Kilogram")
		), patch.object(frappe.db, "get_value", return_value="BOM-1"), patch.object(
			frappe.db, "commit"
		):
			_engine.manufacture_concentrate("Dairy Meal 18", qty=1000)
		self.assertEqual(seen["qty"], 1000)

	def test_it_is_not_for_a_herd(self):
		"""The cost centre chain then falls to the per-company row, which is
		correct: there is no herd to charge a store mix to."""
		from upande_livestock.serverscripts.feeding import _engine

		seen = {}

		def spy(item, bom_no, qty, what, **kw):
			seen["herd"] = kw.get("herd")
			return {"work_order": "WO-1"}

		with patch.object(_engine, "_run_manufacture", side_effect=spy), patch.object(
			frappe, "get_doc", return_value=frappe._dict(name="BOM-1", item="X", quantity=500, uom="Kilogram")
		), patch.object(frappe.db, "get_value", return_value="BOM-1"), patch.object(frappe.db, "commit"):
			_engine.manufacture_concentrate("X", qty=1000)
		self.assertIsNone(seen["herd"])


class TestTheDaysAreGone(unittest.TestCase):
	def test_the_feeding_endpoint_is_gone(self):
		"""Days of cover and head counts were the wrong shape for a mixer, so
		nothing about mixing asks for them any more."""
		with self.assertRaises(ImportError):
			__import__("upande_livestock.serverscripts.feeding.concentrate_plan")

	def test_the_page_no_longer_asks_for_one(self):
		import pathlib

		app = pathlib.Path(frappe.get_app_path("upande_livestock")).parent / "frontend" / "src"
		hits = [str(p) for p in app.rglob("*.ts*") if "concentratePlan" in p.read_text()]
		self.assertEqual(hits, [])

	def test_the_cover_alert_keeps_its_arithmetic(self):
		"""Deliberately NOT deleted with the rest. Cover is counted in days —
		412 kg of calves meal is six weeks for the calves and two days for the
		milkers — and a concentrate running out stops eight herds at once. It
		moved to the alert that needs it instead of dying with the page."""
		from upande_livestock.serverscripts.alerts._cover import concentrate_plan

		self.assertTrue(callable(concentrate_plan))


class TestTheFarmIsFilledIn(unittest.TestCase):
	"""`custom_farm` is mandatory on BOM on this site.

	The unit tests above mock the BOM document, so they cannot see a mandatory
	field refuse an insert — and the first real save did:

	    MandatoryError: [BOM, BOM-ZZ Scaling Probe Meal-001]: custom_farm

	A concentrate has no previous ration to inherit a farm from the way a herd's
	does, so it falls back the same way `_standing_ration._farm_for` does: to the
	farm of the store the feed comes out of. Not hardcoded, because this group
	runs seven farms.
	"""

	def test_it_falls_back_to_the_stores_farm(self):
		with patch.object(CN, "_farm_for_concentrate", return_value="Kapkolia") as asked:
			seen = {}

			def spy(item, lines, base_qty, farm=None, template=None):
				seen["farm"] = farm
				return "BOM-X-001"

			with patch.object(CN, "feed_item_for", return_value="X"), patch.object(
				CN, "_build_concentrate", side_effect=spy
			), patch.object(CN, "_matching_concentrate", return_value=None):
				CN.set_concentrate("X", [{"item_code": "Maize Germ", "qty": 1}], 500)
		self.assertTrue(asked.called)
		self.assertEqual(seen["farm"], "Kapkolia")

	def test_a_farm_given_explicitly_wins(self):
		seen = {}

		def spy(item, lines, base_qty, farm=None, template=None):
			seen["farm"] = farm
			return "BOM-X-001"

		with patch.object(CN, "feed_item_for", return_value="X"), patch.object(
			CN, "_build_concentrate", side_effect=spy
		), patch.object(CN, "_matching_concentrate", return_value=None), patch.object(
			CN, "_farm_for_concentrate", side_effect=AssertionError("must not be asked")
		):
			CN.set_concentrate("X", [{"item_code": "Maize Germ", "qty": 1}], 500, farm="Karen")
		self.assertEqual(seen["farm"], "Karen")
