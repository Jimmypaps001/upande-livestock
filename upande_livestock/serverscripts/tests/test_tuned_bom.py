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


def _two_herds_sharing_a_bom():
	"""Two distinct herds whose Herds.bom is the SAME BOM — the shared-standing-
	ration case (BOM-TMR Calves Meal-011 for 0-2/2-4 on this site). Returns
	(herd_a, herd_b) or (None, None)."""
	rows = frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"])
	by_bom = {}
	for row in rows:
		by_bom.setdefault(row.bom, []).append(row.name)
	for herds in by_bom.values():
		if len(herds) >= 2:
			return herds[0], herds[1]
	return None, None


def _two_herds_with_different_items():
	"""Two herds whose standing BOMs make different production items —
	fixtures for proving a base_bom is refused when it is for the wrong item."""
	rows = frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"])
	items = {row.name: frappe.db.get_value("BOM", row.bom, "item") for row in rows}
	names = list(items)
	for i, a in enumerate(names):
		for b in names[i + 1 :]:
			if items[a] and items[b] and items[a] != items[b]:
				return a, b
	return None, None


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


class TestTunedBomBatchSize(IntegrationTestCase):
	"""Reuse must match on BOM.quantity too, not only on the lines.

	`_engine.manufacture_herd_feed` reads `per_head = flt(bom.quantity)` and
	multiplies the whole run by it. A non-default BOM for the same item with
	byte-identical lines but `quantity = 100` was therefore a valid match for a
	tune of a `quantity = 1` herd BOM — and reusing it scaled the run a
	hundredfold, silently, with no shortage warning until four Stock Entries had
	already been sized from it.
	"""

	def setUp(self):
		self.herd = _a_herd()
		self.base = frappe.get_doc("BOM", frappe.db.get_value("Herds", self.herd, "bom"))
		self.lines = [{"item_code": row.item_code, "qty": flt(row.qty)} for row in self.base.items]
		self.lines[0]["qty"] = flt(self.lines[0]["qty"]) + 7

	def tearDown(self):
		frappe.db.rollback()

	def _decoy_at(self, quantity):
		"""A submitted, active, non-default BOM carrying exactly the tune we are
		about to ask for, but built at a different batch size."""
		doc = frappe.copy_doc(self.base)
		doc.is_active = 1
		doc.is_default = 0
		doc.quantity = quantity
		by_item = {row.item_code: row for row in self.base.items}
		doc.set("items", [])
		for row in self.lines:
			base_row = by_item[row["item_code"]]
			doc.append(
				"items",
				{
					"item_code": row["item_code"],
					"item_name": base_row.item_name,
					"qty": row["qty"],
					"uom": base_row.uom,
					"stock_uom": base_row.stock_uom,
					"conversion_factor": base_row.conversion_factor,
				},
			)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_a_matching_tune_at_another_batch_size_is_not_reused(self):
		decoy = self._decoy_at(flt(self.base.quantity) + 99)
		name = tuned_bom(self.herd, self.lines)
		self.assertNotEqual(
			name,
			decoy.name,
			"a BOM with the same lines but a different batch size scales the run by "
			"quantity, so it is not an equivalent recipe",
		)
		self.assertEqual(flt(frappe.db.get_value("BOM", name, "quantity")), flt(self.base.quantity))

	def test_a_matching_tune_at_the_same_batch_size_is_still_reused(self):
		"""The control — the guard must not defeat reuse, which is the whole
		reason _existing_match exists."""
		decoy = self._decoy_at(flt(self.base.quantity))
		self.assertEqual(tuned_bom(self.herd, self.lines), decoy.name)


class TestTunedBomWithBaseBom(IntegrationTestCase):
	"""`base_bom` lets a tune start from a previously-used recipe instead of
	always from Herds.bom — see herd_recipes.py, the picker this feeds."""

	def setUp(self):
		self.herd = _a_herd()
		self.base = frappe.get_doc("BOM", frappe.db.get_value("Herds", self.herd, "bom"))
		self.lines = [
			{"item_code": row.item_code, "qty": flt(row.qty)} for row in self.base.items
		]

	def tearDown(self):
		frappe.db.rollback()

	def _tuned(self, bump=3):
		lines = [dict(row) for row in self.lines]
		lines[0]["qty"] = flt(lines[0]["qty"]) + bump
		return lines

	def test_no_base_bom_behaves_exactly_as_before(self):
		"""base_bom=None (the default) must still copy from Herds.bom."""
		name = tuned_bom(self.herd, self._tuned())
		doc = frappe.get_doc("BOM", name)
		self.assertEqual(doc.item, self.base.item)
		self.assertEqual(doc.custom_herd, self.herd)
		self.assertEqual(doc.custom_ration_kind, "Tuned")
		self.assertEqual(frappe.db.get_value("Herds", self.herd, "bom"), self.base.name)

	def test_no_base_bom_untuned_passthrough_is_unchanged(self):
		self.assertEqual(tuned_bom(self.herd, self.lines, base_bom=None), self.base.name)

	def test_the_herds_own_standing_bom_is_itself_an_accepted_base(self):
		"""Naming the standing BOM explicitly is equivalent to the default."""
		name = tuned_bom(self.herd, self._tuned(4), base_bom=self.base.name)
		doc = frappe.get_doc("BOM", name)
		self.assertEqual(doc.item, self.base.item)

	def test_tuning_from_a_previously_used_recipe_copies_from_it(self):
		"""Mint a 'previously used recipe' first (a tuned BOM), then tune again
		from that recipe rather than from Herds.bom."""
		recipe_name = tuned_bom(self.herd, self._tuned(3))
		self.assertNotEqual(recipe_name, self.base.name)
		recipe = frappe.get_doc("BOM", recipe_name)
		recipe_lines = [{"item_code": r.item_code, "qty": flt(r.qty)} for r in recipe.items]

		further = [dict(row) for row in recipe_lines]
		further[0]["qty"] = flt(further[0]["qty"]) + 9

		name = tuned_bom(self.herd, further, base_bom=recipe_name)
		doc = frappe.get_doc("BOM", name)
		self.assertEqual(doc.item, self.base.item)
		self.assertEqual(doc.custom_herd, self.herd)
		self.assertEqual(doc.custom_ration_kind, "Tuned")
		self.assertEqual(doc.is_active, 1)
		self.assertEqual(doc.is_default, 0)
		got = {row.item_code: flt(row.qty) for row in doc.items}
		for line in further:
			self.assertAlmostEqual(got[line["item_code"]], flt(line["qty"]), places=4)
		# Herds.bom is never reassigned, no matter which base was tuned from.
		self.assertEqual(frappe.db.get_value("Herds", self.herd, "bom"), self.base.name)

	def test_untuned_passthrough_relative_to_a_non_standing_base(self):
		"""Submitting the base's own lines unmodified must return the base
		itself, even when that base is a previously-tuned recipe, not
		Herds.bom — the reuse rule holds relative to whichever base was used."""
		recipe_name = tuned_bom(self.herd, self._tuned(3))
		recipe = frappe.get_doc("BOM", recipe_name)
		recipe_lines = [{"item_code": r.item_code, "qty": flt(r.qty)} for r in recipe.items]
		self.assertEqual(tuned_bom(self.herd, recipe_lines, base_bom=recipe_name), recipe_name)

	def test_a_base_bom_belonging_to_another_herd_is_refused(self):
		"""A tuned recipe minted for one herd of a shared-standing-ration pair
		must not be usable as the base for the other herd, even though both
		share the same production item."""
		herd_a, herd_b = _two_herds_sharing_a_bom()
		if not herd_a:
			self.skipTest("no two herds on kaitet.local share a standing BOM")
		base_a = frappe.get_doc("BOM", frappe.db.get_value("Herds", herd_a, "bom"))
		lines_a = [{"item_code": r.item_code, "qty": flt(r.qty)} for r in base_a.items]
		lines_a[0]["qty"] = flt(lines_a[0]["qty"]) + 3
		recipe_for_a = tuned_bom(herd_a, lines_a)
		self.assertEqual(frappe.db.get_value("BOM", recipe_for_a, "custom_herd"), herd_a)

		base_b = frappe.get_doc("BOM", frappe.db.get_value("Herds", herd_b, "bom"))
		lines_b = [{"item_code": r.item_code, "qty": flt(r.qty)} for r in base_b.items]
		with self.assertRaises(frappe.ValidationError):
			tuned_bom(herd_b, lines_b, base_bom=recipe_for_a)

	def test_a_base_bom_for_the_wrong_item_is_refused(self):
		herd_a, herd_b = _two_herds_with_different_items()
		if not herd_a:
			self.skipTest("no two herds on kaitet.local have different ration items")
		base_a_name = frappe.db.get_value("Herds", herd_a, "bom")
		base_b = frappe.get_doc("BOM", frappe.db.get_value("Herds", herd_b, "bom"))
		lines_b = [{"item_code": r.item_code, "qty": flt(r.qty)} for r in base_b.items]
		with self.assertRaises(frappe.ValidationError):
			tuned_bom(herd_b, lines_b, base_bom=base_a_name)
