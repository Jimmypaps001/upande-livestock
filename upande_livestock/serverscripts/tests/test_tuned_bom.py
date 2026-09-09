import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding._tuned_bom import tuned_bom


def _a_herd():
	name = frappe.db.get_value("Herds", {"bom": ["is", "set"]}, "name")
	if not name:
		raise AssertionError("kaitet.local has no herd with a BOM")
	return name


def _a_herd_with_mixed_uom_row():
	"""A herd whose BOM has at least one line where the recipe UOM differs
	from the item's stock UOM — the real defect case on this site: hay is
	written as 2 kg in the recipe but stocked in BALE at cf 0.07 bale/kg.
	Returns (herd_name, bom_doc, item_code) or (None, None, None)."""
	for row in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"]):
		bom = frappe.get_doc("BOM", row.bom)
		for item in bom.items:
			if item.uom != item.stock_uom:
				return row.name, bom, item.item_code
	return None, None, None


def _an_item_outside(bom):
	"""An enabled stock item that is not already on `bom` — a stand-in for an
	ingredient an operator adds by hand."""
	codes = [row.item_code for row in bom.items]
	return frappe.db.get_value(
		"Item",
		{"disabled": 0, "is_stock_item": 1, "name": ["not in", codes]},
		"name",
	)


class TestTunedBom(IntegrationTestCase):
	def setUp(self):
		self.herd = _a_herd()
		self.base = frappe.get_doc("BOM", frappe.db.get_value("Herds", self.herd, "bom"))
		self.lines = [
			{"item_code": row.item_code, "qty": flt(row.qty)} for row in self.base.items
		]

	def tearDown(self):
		frappe.db.rollback()

	def _tuned(self):
		lines = [dict(row) for row in self.lines]
		lines[0]["qty"] = flt(lines[0]["qty"]) + 3
		return lines

	def test_it_creates_a_submitted_bom(self):
		name = tuned_bom(self.herd, self._tuned())
		doc = frappe.get_doc("BOM", name)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.item, self.base.item)

	def test_the_bom_is_active_but_not_default(self):
		"""ERPNext refuses a Work Order against an inactive BOM — verified on
		this site. is_default = 0 is what keeps it out of the herd's way."""
		doc = frappe.get_doc("BOM", tuned_bom(self.herd, self._tuned()))
		self.assertEqual(doc.is_active, 1)
		self.assertEqual(doc.is_default, 0)

	def test_the_herds_own_bom_is_untouched(self):
		tuned_bom(self.herd, self._tuned())
		self.assertEqual(frappe.db.get_value("Herds", self.herd, "bom"), self.base.name)
		self.assertEqual(
			frappe.db.get_value("Item", self.base.item, "default_bom"), self.base.name
		)

	def test_the_tuned_quantities_land_on_the_bom(self):
		lines = self._tuned()
		doc = frappe.get_doc("BOM", tuned_bom(self.herd, lines))
		got = {row.item_code: flt(row.qty) for row in doc.items}
		for line in lines:
			self.assertAlmostEqual(got[line["item_code"]], flt(line["qty"]), places=4)

	def test_an_identical_tune_is_reused(self):
		"""A farm that mixes the same correction every morning must not
		accumulate a BOM a day."""
		lines = self._tuned()
		first = tuned_bom(self.herd, lines)
		second = tuned_bom(self.herd, [dict(row) for row in lines])
		self.assertEqual(first, second)

	def test_a_different_tune_makes_a_different_bom(self):
		first = tuned_bom(self.herd, self._tuned())
		other = self._tuned()
		other[0]["qty"] = flt(other[0]["qty"]) + 7
		self.assertNotEqual(tuned_bom(self.herd, other), first)

	def test_an_untuned_recipe_returns_the_herds_own_bom(self):
		"""Nothing changed means nothing to create."""
		self.assertEqual(tuned_bom(self.herd, self.lines), self.base.name)

	def test_an_empty_line_list_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			tuned_bom(self.herd, [])

	def test_a_zero_quantity_line_is_dropped(self):
		lines = [dict(row) for row in self.lines]
		lines[0]["qty"] = 0
		doc = frappe.get_doc("BOM", tuned_bom(self.herd, lines))
		self.assertNotIn(lines[0]["item_code"], [row.item_code for row in doc.items])

	def test_duplicate_item_codes_are_merged_by_summing(self):
		"""Submitting the same ingredient twice means 'this much in total',
		not two BOM Item rows for the same item."""
		lines = [dict(row) for row in self.lines]
		dup = lines[0]
		half = flt(dup["qty"]) / 2
		lines[0] = {"item_code": dup["item_code"], "qty": half}
		lines.append({"item_code": dup["item_code"], "qty": flt(dup["qty"]) + 3 - half})
		doc = frappe.get_doc("BOM", tuned_bom(self.herd, lines))
		rows = [row for row in doc.items if row.item_code == dup["item_code"]]
		self.assertEqual(len(rows), 1)
		self.assertAlmostEqual(flt(rows[0].qty), flt(dup["qty"]) + 3, places=4)


class TestTunedBomUom(IntegrationTestCase):
	"""The bug found in review: a tuned line's qty is in the *recipe's* UOM
	for that item, not the item's stock UOM. Building a BOM Item row from
	``item.stock_uom`` with ``conversion_factor=1`` silently multiplies any
	mixed-UOM ingredient's stock_qty by the wrong factor, and ERPNext's own
	``BOM.update_stock_qty`` cannot catch it because a hardcoded 1 is
	truthy — the recompute only runs ``if not m.conversion_factor``."""

	def setUp(self):
		self.herd, self.base, self.mixed_item = _a_herd_with_mixed_uom_row()
		if not self.herd:
			self.skipTest(
				"no herd BOM on kaitet.local has a line whose recipe UOM differs "
				"from its stock UOM — the mixed-UOM regression cannot be exercised"
			)
		self.mixed_row = next(r for r in self.base.items if r.item_code == self.mixed_item)
		self.lines = [
			{"item_code": row.item_code, "qty": flt(row.qty)} for row in self.base.items
		]

	def tearDown(self):
		frappe.db.rollback()

	def test_a_mixed_uom_line_keeps_the_base_boms_conversion(self):
		lines = [dict(row) for row in self.lines]
		for line in lines:
			if line["item_code"] == self.mixed_item:
				line["qty"] = flt(line["qty"]) + 1

		doc = frappe.get_doc("BOM", tuned_bom(self.herd, lines))
		row = next(r for r in doc.items if r.item_code == self.mixed_item)

		self.assertEqual(row.uom, self.mixed_row.uom)
		self.assertAlmostEqual(
			flt(row.conversion_factor), flt(self.mixed_row.conversion_factor), places=6
		)
		expected_qty = flt(self.mixed_row.qty) + 1
		self.assertAlmostEqual(
			flt(row.stock_qty), expected_qty * flt(self.mixed_row.conversion_factor), places=4
		)

	def test_an_added_item_falls_back_to_stock_uom(self):
		new_item = _an_item_outside(self.base)
		if not new_item:
			self.skipTest("no item on kaitet.local is free to add to this BOM")

		lines = [dict(row) for row in self.lines]
		lines.append({"item_code": new_item, "qty": 4})
		doc = frappe.get_doc("BOM", tuned_bom(self.herd, lines))
		row = next(r for r in doc.items if r.item_code == new_item)

		stock_uom = frappe.db.get_value("Item", new_item, "stock_uom")
		self.assertEqual(row.uom, stock_uom)
		self.assertEqual(flt(row.conversion_factor), 1.0)
		self.assertAlmostEqual(flt(row.stock_qty), 4.0, places=4)

	def test_an_untuned_recipe_still_returns_the_herds_own_bom(self):
		"""The passthrough path must stay green with the fix in place — an
		unmodified recipe still creates nothing."""
		self.assertEqual(tuned_bom(self.herd, self.lines), self.base.name)
