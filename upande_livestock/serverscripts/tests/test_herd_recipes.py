import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding._tuned_bom import tuned_bom
from upande_livestock.serverscripts.feeding.herd_recipes import herd_recipes


def _a_shared_standing_bom_herd_missed_by_custom_herd():
	"""A herd sharing its Herds.bom with another herd, picked so that the
	shared BOM's own `custom_herd` does NOT name this herd — the case a
	`custom_herd`-only lookup gets wrong. `custom_herd` may be blank (the
	original backfill rule) or may name the *other* herd of the pair (a later
	backfill rule attributing a shared BOM to whichever herd it judges fed
	first); either way this herd is the one a naive query would miss.
	Returns (herd_name, bom_name) or (None, None)."""
	rows = frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"])
	by_bom = {}
	for row in rows:
		by_bom.setdefault(row.bom, []).append(row.name)
	for bom, herds in by_bom.items():
		if len(herds) < 2:
			continue
		custom_herd = frappe.db.get_value("BOM", bom, "custom_herd")
		for herd in herds:
			if herd != custom_herd:
				return herd, bom
	return None, None


def _a_herd_with_mixed_uom_row():
	"""A herd whose standing BOM has at least one line where the recipe UOM
	differs from the item's stock UOM (hay on this site: 2-5 kg in the
	recipe, stocked in BALE at cf 0.07). Returns (herd, bom_name, BOM Item
	row) or (None, None, None)."""
	for row in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"]):
		for item in frappe.get_all(
			"BOM Item",
			filters={"parent": row.bom},
			fields=["item_code", "qty", "uom", "stock_qty", "stock_uom"],
		):
			if item.uom != item.stock_uom:
				return row.name, row.bom, item
	return None, None, None


class TestHerdRecipes(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_standing_ration_of_a_shared_bom_herd_comes_from_herds_bom(self):
		"""Herds.bom must answer this even for the herd of a shared pair that
		`custom_herd` does not name — a naive custom_herd-only implementation
		gets this case wrong."""
		herd, bom = _a_shared_standing_bom_herd_missed_by_custom_herd()
		if not herd:
			self.skipTest(
				"no shared-standing-BOM herd on kaitet.local is missed by custom_herd"
			)
		res = herd_recipes(herd)
		self.assertTrue(res["ok"], res.get("error"))
		self.assertEqual(res["standing_bom"], bom)
		standing = [r for r in res["recipes"] if r["is_standing"]]
		self.assertEqual(len(standing), 1)
		self.assertEqual(standing[0]["bom_no"], bom)
		self.assertEqual(standing[0]["kind"], "Standing")

	def test_lines_come_back_in_recipe_uom_not_stock_uom(self):
		"""Hay is written as kg on every herd BOM checked but stocked in BALE
		at cf 0.07 — returning stock_qty/stock_uom here would feed the ~14x
		bug straight into a picker."""
		herd, bom, item = _a_herd_with_mixed_uom_row()
		if not herd:
			self.skipTest("no herd BOM on kaitet.local has a mixed-UOM line")
		res = herd_recipes(herd)
		self.assertTrue(res["ok"], res.get("error"))
		standing = next(r for r in res["recipes"] if r["is_standing"])
		self.assertEqual(standing["bom_no"], bom)
		line = next(l for l in standing["lines"] if l["item_code"] == item.item_code)
		self.assertEqual(line["uom"], item.uom)
		self.assertAlmostEqual(flt(line["qty"]), flt(item.qty), places=4)
		self.assertNotAlmostEqual(flt(line["qty"]), flt(item.stock_qty), places=4)

	def test_a_missing_herd_is_refused(self):
		res = herd_recipes("Not A Real Herd On This Site")
		self.assertIn("error", res)

	def test_tuned_recipes_are_scoped_to_the_herd_and_come_back_newest_first(self):
		herd = frappe.db.get_value("Herds", {"bom": ["is", "set"]}, "name")
		base = frappe.get_doc("BOM", frappe.db.get_value("Herds", herd, "bom"))
		lines = [{"item_code": r.item_code, "qty": flt(r.qty)} for r in base.items]

		lines[0]["qty"] = flt(lines[0]["qty"]) + 3
		first = tuned_bom(herd, lines)

		lines2 = [dict(row) for row in lines]
		lines2[0]["qty"] = flt(lines2[0]["qty"]) + 5
		second = tuned_bom(herd, lines2)

		res = herd_recipes(herd)
		self.assertTrue(res["ok"], res.get("error"))
		tuned_names = [r["bom_no"] for r in res["recipes"] if not r["is_standing"]]
		self.assertIn(first, tuned_names)
		self.assertIn(second, tuned_names)
		self.assertLess(
			tuned_names.index(second),
			tuned_names.index(first),
			"the newer tune should come before the older one",
		)
		for r in res["recipes"]:
			if not r["is_standing"]:
				self.assertEqual(r["kind"], "Tuned")
