# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Making and revising a concentrate: a recipe for the store, not for a herd.

A concentrate is an ingredient of a TMR and a product in its own right. The
farm mixes a batch of it, it sits in the concentrate store, and the TMR run
consumes it. Nothing about that involves cows.

The page it backs used to be driven by `concentrate_plan(days)` — every herd's
per-head concentrate line, times head count, times days of cover, rounded up to
whole batches. That is a herd-shaped, calendar-shaped answer to a question with
neither shape, and it is gone. The mixer takes a tonne of ingredients and makes
a tonne of meal whether there are forty cows in the shed or none.

## The base is not the sum of the lines

This is where a concentrate parts company with a standing ration, and it is why
`_standing_ration._build` could not simply be reused.

A ration's `BOM.quantity` IS the sum of its lines: a ration is what one animal
eats in a day, so the per-head total is the definition. A concentrate's
ingredients are stated against an output the farm declares — 500 kg of meal
from lines that may not add to 500, because of moisture, or because the recipe
is written in round numbers a mixer operator can work to. So the base is typed,
and stored as the BOM quantity.

Manufacturing then scales: 1000 kg off a 500 kg base consumes exactly twice the
lines. That is ERPNext's own Work Order scaling, not arithmetic this app does —
which matters, because it means the consumption the ledger records is the one
ERPNext computed from the recipe, not one we handed it.

## Revisions

The same discipline the standing ration keeps: saving a recipe that already
exists returns it untouched rather than minting one that says the same thing.
This site's BOM list is already what happens when every save makes a revision.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.feeding._standing_ration import feed_item_for
from upande_livestock.serverscripts.feeding._tuned_bom import _clean

#: `BOM.custom_ration_kind`. Standing and Tuned are a herd's; this is neither.
CONCENTRATE = "Concentrate"


def concentrate_items():
	"""Item codes that ARE a concentrate, by the only rule that decides it.

	`feed_in_store._ration_roles` — a BOM line that is itself manufactured
	(`_sub_bom_for`) or named bought-in on Livestock Settings. The Ration
	Editor highlights on exactly this, and so does the feed run.

	It is deliberately NOT `custom_ration_kind`. That stamp is written on
	concentrates created here and read by nobody: the page that decided what a
	concentrate was by looking at it listed nothing while the editor
	highlighted five in the same recipes, because no BOM on any site had ever
	carried it. Stamping them all would have closed that for a day and left the
	two rules free to drift again.
	"""
	try:
		from upande_livestock.serverscripts.feeding.feed_in_store import _ration_roles

		return _ration_roles()[1]
	except Exception:
		return set()


def total_of(lines):
	"""What a recipe weighs: the sum of its ingredients.

	NOT a figure the farm types. That was the first shape of this and it
	permits 5000 kg and 6000 kg of ingredients producing 100 kg of meal, which
	is not a recipe anyone can check against a mixer. A ration's quantity has
	always been the sum of its lines; a concentrate's is too.
	"""
	return sum(flt(row.get("qty")) for row in lines or [])


def _signature(lines):
	"""What makes one recipe the same as another: its lines, order-insensitive."""
	return sorted((row["item_code"], round(flt(row["qty"]), 4)) for row in lines)


def _matching_concentrate(item, signature, base_qty):
	"""An existing submitted concentrate BOM that already says exactly this."""
	for bom in frappe.get_all(
		"BOM",
		filters={"item": item, "docstatus": 1, "custom_ration_kind": CONCENTRATE},
		fields=["name", "quantity"],
		order_by="creation desc",
	):
		if abs(flt(bom.quantity) - flt(base_qty)) >= 0.0005:
			continue
		rows = frappe.get_all("BOM Item", filters={"parent": bom.name}, fields=["item_code", "qty"])
		if _signature([{"item_code": r.item_code, "qty": r.qty} for r in rows]) == signature:
			return bom.name
	return None


def _build_concentrate(item, lines, farm=None, template=None):
	"""A fresh submitted BOM of `item` from `lines`, weighing what they weigh.

	`template` is the recipe being revised, and it is borrowed for the same
	reason `_standing_ration._build` borrows one: the row UOMs travel with it.
	An ingredient written in kilograms but stocked in bales, re-added without
	the old row's UOM, is read as bales — fourteen times the feed, and
	plausible enough to miss.
	"""
	old_row_by_item = {row.item_code: row for row in (template.items if template else [])}

	doc = frappe.copy_doc(template) if template else frappe.new_doc("BOM")
	doc.item = item
	# The sum of the lines. A recipe whose stated output contradicts its inputs
	# cannot be checked against the mixer — see `total_of`.
	doc.quantity = total_of(lines)
	doc.is_active = 1
	doc.is_default = 1
	doc.with_operations = 0
	# Mixed for the store. A concentrate stamped with a herd would be offered
	# as that herd's own ration by every page that reads `custom_herd`.
	doc.custom_herd = None
	doc.custom_is_livestock_feed = 1
	doc.custom_ration_kind = CONCENTRATE
	if farm and doc.meta.has_field("custom_farm") and not doc.get("custom_farm"):
		# Mandatory on BOM on this site — the first real save refused without
		# it. See `_farm_for_concentrate` for where the value comes from.
		doc.custom_farm = farm
	if not doc.get("company"):
		doc.company = frappe.db.get_single_value("Livestock Settings", "custom_default_company")

	doc.set("items", [])
	for row in lines:
		item_doc = frappe.get_cached_doc("Item", row["item_code"])
		old = old_row_by_item.get(row["item_code"])
		doc.append(
			"items",
			{
				"item_code": row["item_code"],
				"item_name": item_doc.item_name,
				"qty": row["qty"],
				"uom": old.uom if old else item_doc.stock_uom,
				"stock_uom": item_doc.stock_uom,
				"conversion_factor": old.conversion_factor if old else 1,
			},
		)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def _farm_for_concentrate(previous=None):
	"""`custom_farm` is mandatory on BOM here, and a concentrate has no herd to
	inherit one from.

	The recipe being revised first, then the farm of the store the feed comes
	out of — the same fallback `_standing_ration._farm_for` makes, and not
	hardcoded, because this group runs seven farms.
	"""
	if previous:
		farm = frappe.db.get_value("BOM", previous, "custom_farm")
		if farm:
			return farm
	store = frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse")
	return frappe.db.get_value("Warehouse", store, "custom_farm") if store else None


def set_concentrate(name, lines, farm=None):
	"""Create or revise a concentrate. Returns what it is now.

	`name` is what the farm calls it, and creates the Item the first time it is
	used — `BOM.item` is required, so a recipe has to be a recipe FOR
	something, and choosing that product is not a decision to put in front of
	someone mid-recipe. See `_standing_ration.feed_item_for`.
	"""
	name = (name or "").strip()
	if not name:
		frappe.throw(_("Name this concentrate."))

	lines = _clean(lines)
	if not lines:
		frappe.throw(_("A concentrate needs at least one ingredient."))

	base_qty = total_of(lines)
	if base_qty <= 0:
		frappe.throw(_("A concentrate has to weigh something."))

	item = feed_item_for(name)
	signature = _signature(lines)

	found = _matching_concentrate(item, signature, base_qty)
	if found:
		return {"bom": found, "item": item, "base_qty": base_qty, "changed": False}

	previous = frappe.db.get_value(
		"BOM",
		{"item": item, "docstatus": 1, "custom_ration_kind": CONCENTRATE},
		"name",
		order_by="creation desc",
	)
	template = frappe.get_doc("BOM", previous) if previous else None
	bom = _build_concentrate(
		item, lines, farm=farm or _farm_for_concentrate(previous), template=template
	)
	return {"bom": bom, "item": item, "base_qty": base_qty, "changed": True, "superseded": previous}


def concentrate_list(qty_by_item=None):
	"""Every concentrate the farm mixes, with its recipe priced against the stores.

	Listed by `concentrate_items` — the rule the Ration Editor highlights on —
	NOT by `custom_ration_kind`, which nothing outside this module has ever
	carried. That mismatch is why this page came back empty while the editor
	showed five in the same recipes.

	Each one carries its ingredients as `resolve_requirement` returns them, so
	the page shows what the Feeding page already shows: what the line needs,
	which store it would come from, what is there, and how far short that is.
	`qty_by_item` scales one concentrate's lines to the tonnage the operator is
	about to mix; unscaled, the lines are the recipe as written.

	No herd, no head count, no days.
	"""
	from upande_livestock.serverscripts.feeding import _engine

	qty_by_item = qty_by_item or {}
	store = _engine._feed_store()

	out = []
	for item in sorted(concentrate_items()):
		bom = _newest_bom(item)
		if not bom:
			# A concentrate the engine recognises that has no submitted recipe
			# of its own is a bought-in one: real, and nothing to mix here.
			continue
		want = flt(qty_by_item.get(item)) or flt(bom.quantity) or 1.0
		try:
			_bom, lines = _engine.resolve_requirement(bom.name, want)
		except Exception:
			# Pricing a recipe against the stores must not cost the whole list.
			lines = []
		out.append(
			{
				"item_code": item,
				"item_name": bom.item_name or item,
				"bom_no": bom.name,
				"base_qty": flt(bom.quantity),
				"uom": bom.uom,
				"mix_qty": want,
				"lines": lines,
				"in_store": _on_hand(item, store),
				"stores": _where_it_is(item),
			}
		)
	out.sort(key=lambda r: (r["item_name"] or "").lower())
	return out


def _newest_bom(item):
	"""The active recipe for `item`, newest first. None if it has none."""
	rows = frappe.get_all(
		"BOM",
		filters={"item": item, "docstatus": 1, "is_active": 1},
		fields=["name", "item_name", "quantity", "uom"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def _where_it_is(item_code):
	"""How much of the finished concentrate sits in each store that holds any.

	Never summed: a tonne spread over three stores is not a tonne the next TMR
	run can draw on, and the page says which store to go to.
	"""
	return [
		{"warehouse": r.warehouse, "qty": flt(r.actual_qty)}
		for r in frappe.get_all(
			"Bin",
			filters={"item_code": item_code, "actual_qty": [">", 0]},
			fields=["warehouse", "actual_qty"],
			order_by="actual_qty desc",
		)
	]


def _on_hand(item_code, warehouse):
	"""How much of it is in the concentrate store. Never summed across stores —
	a figure from somewhere else is not stock the next TMR run can consume."""
	if not warehouse:
		return 0.0
	return flt(
		frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
	)
