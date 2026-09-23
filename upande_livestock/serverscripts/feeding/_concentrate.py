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


def _build_concentrate(item, lines, base_qty, farm=None, template=None):
	"""A fresh submitted BOM making `base_qty` of `item` from `lines`.

	`template` is the recipe being revised, and it is borrowed for the same
	reason `_standing_ration._build` borrows one: the row UOMs travel with it.
	An ingredient written in kilograms but stocked in bales, re-added without
	the old row's UOM, is read as bales — fourteen times the feed, and
	plausible enough to miss.
	"""
	old_row_by_item = {row.item_code: row for row in (template.items if template else [])}

	doc = frappe.copy_doc(template) if template else frappe.new_doc("BOM")
	doc.item = item
	# The declared output, NOT the sum of the lines. See the module docstring.
	doc.quantity = flt(base_qty)
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


def set_concentrate(name, lines, base_qty, farm=None):
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

	base_qty = flt(base_qty)
	if base_qty <= 0:
		frappe.throw(_("Say how much these ingredients make."))

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
		item, lines, base_qty, farm=farm or _farm_for_concentrate(previous), template=template
	)
	return {"bom": bom, "item": item, "base_qty": base_qty, "changed": True, "superseded": previous}


def concentrate_list():
	"""Every concentrate the farm has, with its recipe and what is in store.

	No herd, no head count, no days — the three things the page this backs used
	to be built out of.
	"""
	from upande_livestock.serverscripts.feeding import _engine, _recipe_lines

	boms = frappe.get_all(
		"BOM",
		filters={"docstatus": 1, "is_active": 1, "custom_ration_kind": CONCENTRATE},
		fields=["name", "item", "item_name", "quantity", "uom"],
		order_by="item asc, creation desc",
	)

	# One row per concentrate: the newest active recipe wins, older revisions
	# are history and belong on the BOM list, not on a page for mixing today.
	newest = {}
	for bom in boms:
		newest.setdefault(bom.item, bom)

	lines_by_bom = _recipe_lines.lines_for([b.name for b in newest.values()])
	store = _engine._feed_store()

	out = []
	for item, bom in newest.items():
		out.append(
			{
				"item_code": item,
				"item_name": bom.item_name or item,
				"bom_no": bom.name,
				"base_qty": flt(bom.quantity),
				"uom": bom.uom,
				"lines": lines_by_bom.get(bom.name, []),
				"in_store": _on_hand(item, store),
			}
		)
	out.sort(key=lambda r: (r["item_name"] or "").lower())
	return out


def _on_hand(item_code, warehouse):
	"""How much of it is in the concentrate store. Never summed across stores —
	a figure from somewhere else is not stock the next TMR run can consume."""
	if not warehouse:
		return 0.0
	return flt(
		frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
	)
