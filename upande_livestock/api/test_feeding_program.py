# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The herd feeding programme — what the two sections promise.

A herd's TMR is manufactured single-level, so the concentrate it lists is
consumed as stock rather than exploded. That makes three things load-bearing,
and each has a test here:

  * requirements scale with head count, not with the BOM's base quantity;
  * requirements are compared in STOCK UOM. Hay is written in Kilogram on every
    herd BOM but stocked in BALE at 0.07 bale/kg — comparing the recipe figure
    against Bin would read ~14x high and green-light a run that cannot post;
  * the same resolver picks the warehouse for the check and for the Work Order,
    so a green check cannot become a negative-stock transfer;
  * a concentrate is recognised whether it is mixed on the farm or bought
    ready-packed. Only the mixed kind has a BOM, and only the mixed kind gets a
    Manufacture button — but both must be flagged as concentrate rather than
    disappearing into the raw materials.

These are read-only against whatever the site holds. They skip rather than fail
when no herd has a BOM, because that is a missing fixture, not a broken feature.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.api import feeding


def _herd_with_bom():
	"""A herd that has both a BOM and animals, or None."""
	rows = frappe.get_all(
		"Herds",
		filters=[["bom", "is", "set"], ["number_of_animals", ">", 0]],
		fields=["name", "bom", "number_of_animals"],
		order_by="number_of_animals desc",
		limit=1,
	)
	return rows[0] if rows else None


def _herd_with_concentrate():
	"""A herd whose BOM carries a sub-assembly line, or None."""
	for h in frappe.get_all(
		"Herds", filters=[["bom", "is", "set"], ["number_of_animals", ">", 0]], fields=["name", "bom"]
	):
		for row in frappe.get_all("BOM Item", filters={"parent": h.bom}, fields=["item_code", "bom_no"]):
			if row.bom_no or frappe.db.get_value("Item", row.item_code, "default_bom"):
				return h
	return None


class TestFeedingProgram(IntegrationTestCase):
	def setUp(self):
		self.herd = _herd_with_bom()
		if not self.herd:
			raise unittest.SkipTest("no herd on this site has a BOM and animals")

	def test_total_scales_with_head_count(self):
		p = feeding.get_herd_feeding_program(self.herd.name)
		self.assertEqual(p["heads"], int(self.herd.number_of_animals))
		self.assertAlmostEqual(p["total_manufacture_qty"], p["per_head_qty"] * p["heads"], places=4)

	def test_line_requirements_scale_with_head_count(self):
		"""Every line is its BOM quantity times the head count — the BOM is per head."""
		p = feeding.get_herd_feeding_program(self.herd.name)
		bom = frappe.get_doc("BOM", self.herd.bom)
		base = flt(bom.quantity) or 1.0
		by_item = {ln["item_code"]: ln for ln in p["lines"]}
		for row in bom.items:
			ln = by_item[row.item_code]
			expected = flt(row.stock_qty) * (p["total_manufacture_qty"] / base)
			self.assertAlmostEqual(ln["required_qty"], expected, places=4)

	def test_requirements_are_in_stock_uom(self):
		"""The comparison unit must be the unit Bin counts in, not the recipe's."""
		p = feeding.get_herd_feeding_program(self.herd.name)
		for ln in p["lines"]:
			stock_uom = frappe.db.get_value("Item", ln["item_code"], "stock_uom")
			self.assertEqual(ln["uom"], stock_uom)
			if ln["recipe_uom"] != ln["uom"]:
				# Both figures describe the same physical amount.
				self.assertAlmostEqual(
					ln["required_qty"], ln["recipe_qty"] * ln["conversion_factor"], places=4
				)

	def test_availability_is_read_from_the_chosen_warehouse(self):
		"""`available` is the balance in the warehouse the run would draw from —
		not a total across the farm, which would hide a stranded pile."""
		p = feeding.get_herd_feeding_program(self.herd.name)
		for ln in p["lines"]:
			self.assertIn(ln["source_warehouse"], p["warehouses"])
			self.assertAlmostEqual(
				ln["available"],
				feeding._bin_qty(ln["item_code"], ln["source_warehouse"]),
				places=4,
			)

	def test_shortage_is_the_gap_at_that_warehouse(self):
		p = feeding.get_herd_feeding_program(self.herd.name)
		for ln in p["lines"]:
			self.assertAlmostEqual(
				ln["short_qty"], max(0.0, ln["required_qty"] - ln["available"]), places=4
			)
		self.assertEqual(p["can_manufacture"], not p["shortages"])

	def test_manufacture_refuses_when_short(self):
		"""A short run must not post — the transfer would go negative."""
		p = feeding.get_herd_feeding_program(self.herd.name)
		if p["can_manufacture"]:
			raise unittest.SkipTest("this herd is not short; nothing to refuse")
		with self.assertRaises(frappe.ValidationError):
			feeding.manufacture_herd_feed(self.herd.name)


class TestPickSource(IntegrationTestCase):
	"""_pick_source is the single point both the check and the Work Order use."""

	def test_first_warehouse_that_covers_the_line_wins(self):
		whs = ["A", "B", "C"]
		qtys = {"A": 5.0, "B": 50.0, "C": 500.0}
		orig = feeding._bin_qty
		feeding._bin_qty = lambda item, wh: qtys[wh]
		try:
			self.assertEqual(feeding._pick_source("X", 10.0, whs)[0], "B")
			self.assertEqual(feeding._pick_source("X", 1.0, whs)[0], "A")
			self.assertEqual(feeding._pick_source("X", 100.0, whs)[0], "C")
		finally:
			feeding._bin_qty = orig

	def test_falls_back_to_the_fullest_warehouse_when_none_can_cover(self):
		"""So the shortfall is reported against a real place, not an arbitrary one."""
		whs = ["A", "B", "C"]
		qtys = {"A": 5.0, "B": 50.0, "C": 20.0}
		orig = feeding._bin_qty
		feeding._bin_qty = lambda item, wh: qtys[wh]
		try:
			wh, here, everywhere = feeding._pick_source("X", 1000.0, whs)
			self.assertEqual(wh, "B")
			self.assertAlmostEqual(here, 50.0)
			self.assertAlmostEqual(everywhere, 75.0)
		finally:
			feeding._bin_qty = orig

	def test_empty_warehouse_list_yields_nothing(self):
		self.assertEqual(feeding._pick_source("X", 10.0, []), (None, 0.0, 0.0))


class TestConcentratePlan(IntegrationTestCase):
	def setUp(self):
		self.herd = _herd_with_concentrate()
		if not self.herd:
			raise unittest.SkipTest("no herd on this site has a concentrate in its BOM")

	def test_a_concentrate_line_gets_its_own_plan(self):
		p = feeding.get_herd_feeding_program(self.herd.name)
		conc = {c["item_code"] for c in p["concentrates"]}
		self.assertTrue(conc)
		self.assertEqual(conc, {ln["item_code"] for ln in p["lines"] if ln["is_concentrate"]})

	def test_shortfall_rounds_up_to_whole_batches(self):
		"""A mixer runs batches, not remainders."""
		p = feeding.get_herd_feeding_program(self.herd.name)
		line = next(ln for ln in p["lines"] if ln["is_concentrate"])
		batch = flt(frappe.db.get_value("BOM", line["bom_no"], "quantity")) or 1.0

		# Scale the demand until this line is genuinely short, without touching stock.
		for short in (batch * 0.01, batch * 1.2, batch * 2.0):
			probe = dict(line, short_qty=short)
			plan = feeding._concentrate_plan(probe)
			self.assertGreaterEqual(plan["plan_qty"], short)
			self.assertLess(plan["plan_qty"] - short, batch)
			self.assertEqual(plan["plan_qty"], plan["batches"] * batch)

	def test_no_shortfall_still_costs_one_batch(self):
		"""So the operator can see what a run needs before committing to it."""
		p = feeding.get_herd_feeding_program(self.herd.name)
		line = next(ln for ln in p["lines"] if ln["is_concentrate"])
		plan = feeding._concentrate_plan(dict(line, short_qty=0.0))
		self.assertEqual(plan["batches"], 0)
		self.assertFalse(plan["needed"])
		self.assertAlmostEqual(plan["plan_qty"], plan["batch_qty"], places=4)


class TestFeedSourceWarehouses(IntegrationTestCase):
	def test_the_wip_store_is_always_a_candidate(self):
		"""A concentrate manufactured here lands in the store; the TMR run that
		follows has to be able to consume it from there."""
		self.assertIn(feeding._feed_store(), feeding._feed_source_warehouses())

	def test_configured_order_is_preserved(self):
		configured = [
			r.warehouse
			for r in frappe.get_all(
				"Livestock Feed Warehouse",
				filters={"parenttype": "Livestock Settings"},
				fields=["warehouse"],
				order_by="idx asc",
			)
		]
		if not configured:
			raise unittest.SkipTest("no feed source warehouses configured on this site")
		self.assertEqual(feeding._feed_source_warehouses()[: len(configured)], configured)


class TestConcentrateKinds(IntegrationTestCase):
	"""Mixed and bought-in concentrates are both concentrates, and only one of
	them can be manufactured."""

	def test_a_line_with_a_bom_is_mixed(self):
		herd = _herd_with_concentrate()
		if not herd:
			raise unittest.SkipTest("no herd on this site has a concentrate in its BOM")
		p = feeding.get_herd_feeding_program(herd.name)
		for ln in p["lines"]:
			if ln["bom_no"]:
				self.assertEqual(ln["concentrate_source"], "Mixed")
				self.assertTrue(ln["is_concentrate"])

	def test_a_listed_item_is_bought_in(self):
		"""Nothing in the item data separates a bought-in concentrate from silage
		— it is a concentrate only because Livestock Settings says so."""
		listed = feeding._bought_in_concentrates()
		if not listed:
			raise unittest.SkipTest("no bought-in concentrates configured on this site")
		for h in frappe.get_all(
			"Herds", filters=[["bom", "is", "set"], ["number_of_animals", ">", 0]], fields=["name"]
		):
			p = feeding.get_herd_feeding_program(h.name)
			for ln in p["lines"]:
				if ln["item_code"] in listed:
					self.assertEqual(ln["concentrate_source"], "Bought in")
					self.assertTrue(ln["is_concentrate"])
					self.assertIsNone(ln["bom_no"])

	def test_plain_raw_materials_stay_unflagged(self):
		herd = _herd_with_bom()
		if not herd:
			raise unittest.SkipTest("no herd on this site has a BOM and animals")
		p = feeding.get_herd_feeding_program(herd.name)
		listed = feeding._bought_in_concentrates()
		for ln in p["lines"]:
			if not ln["bom_no"] and ln["item_code"] not in listed:
				self.assertIsNone(ln["concentrate_source"])
				self.assertFalse(ln["is_concentrate"])

	def test_a_bought_in_plan_offers_no_work_order(self):
		"""Its card must not carry a Manufacture button — there is nothing to run."""
		listed = feeding._bought_in_concentrates()
		if not listed:
			raise unittest.SkipTest("no bought-in concentrates configured on this site")
		seen = False
		for h in frappe.get_all(
			"Herds", filters=[["bom", "is", "set"], ["number_of_animals", ">", 0]], fields=["name"]
		):
			p = feeding.get_herd_feeding_program(h.name)
			for c in p["concentrates"]:
				if c["source"] != "Bought in":
					continue
				seen = True
				self.assertFalse(c["can_manufacture"])
				self.assertIsNone(c["bom_no"])
				self.assertEqual(c["batches"], 0)
				self.assertEqual(c["lines"], [])
		if not seen:
			raise unittest.SkipTest("no herd draws on a bought-in concentrate")

	def test_every_concentrate_line_gets_a_card(self):
		"""Both kinds reach the second section — a bought-in one must not fall
		through into the raw materials and lose its section."""
		for h in frappe.get_all(
			"Herds", filters=[["bom", "is", "set"], ["number_of_animals", ">", 0]], fields=["name"]
		):
			p = feeding.get_herd_feeding_program(h.name)
			self.assertEqual(
				{c["item_code"] for c in p["concentrates"]},
				{ln["item_code"] for ln in p["lines"] if ln["is_concentrate"]},
			)
