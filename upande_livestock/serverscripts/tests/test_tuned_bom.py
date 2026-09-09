import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding._tuned_bom import tuned_bom


def _a_herd():
	name = frappe.db.get_value("Herds", {"bom": ["is", "set"]}, "name")
	if not name:
		raise AssertionError("kaitet.local has no herd with a BOM")
	return name


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
