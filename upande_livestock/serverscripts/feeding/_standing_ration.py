# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A herd's standing ration, and what it means to change one.

ONE BOM PER HERD, REVISED OVER TIME — the farm's words. `Herds.bom` is that
BOM, and everything downstream reads the ration off it: the day's requirement,
the concentrate plan, the shortage check, the Work Order.

A CHANGE MAKES A NEW BOM. It cannot do anything else. A submitted BOM seals —
ERPNext answers an edit with "Not allowed to change Qty after submission from
35.0 to 36.0" — so there is nowhere to put the new numbers. That turns out to
be the behaviour you want anyway: every feed run ever posted points at the BOM
it was mixed from, and rewriting that recipe in place would silently restate
what the farm fed last March. So the old revision stays submitted and readable,
and the herd is pointed at the new one.

A RECIPE IS ITS LINES AND ITS OUTPUT. `_engine` reads `per_head =
flt(bom.quantity)` and scales the entire run by it, so two BOMs with identical
lines and quantities of 1 and 100 make runs that differ by a hundredfold. Both
halves are therefore part of what "the same recipe" means — see
`build_feed_rations` for what happens when they disagree.

The output is the sum of the lines, not a free parameter. One run of a herd's
BOM makes one animal's ration for one day; the lines are the per-head amounts;
they add up to it. `BOM.uom` is not ours to choose — `BOM.validate_main_item`
overwrites it with the item's stock UOM on every save.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.feeding._tuned_bom import (
	_carry_forward,
	_clean,
	_signature,
)

STANDING = "Standing"


def per_head_kg(lines):
	"""What one animal's ration weighs — the BOM's output quantity."""
	return flt(sum(flt(row["qty"]) for row in lines))


def _matching(item, signature, quantity):
	"""A submitted BOM for `item` that already says exactly this.

	Any submitted BOM, default or not: a farm that revises a ration and revises
	it back should land on the recipe it had, not mint a third copy of it. The
	quantity is matched too, for the reason in the module docstring.
	"""
	for name in frappe.get_all(
		"BOM",
		filters={"item": item, "docstatus": 1, "quantity": flt(quantity)},
		pluck="name",
		order_by="creation desc",
	):
		rows = frappe.get_all("BOM Item", filters={"parent": name},
		                      fields=["item_code", "qty"])
		if _signature([{"item_code": r.item_code, "qty": r.qty} for r in rows]) == signature:
			return name
	return None


def _adopt(bom_name, herd, farm=None):
	"""Make an existing BOM this herd's standing ration, mending it on the way.

	`BOM.is_default` and `Item.default_bom` are two halves of one fact that
	ERPNext keeps in step through `manage_default_bom` — which a `db.set_value`
	walks straight past. A ration adopted from an older build can therefore be
	the default while the item points at nothing, which reads as "this herd has
	no recipe" everywhere except the BOM itself.
	"""
	item = frappe.db.get_value("BOM", bom_name, "item")
	values = {"is_active": 1, "is_default": 1,
	          "custom_herd": herd, "custom_is_livestock_feed": 1,
	          "custom_ration_kind": STANDING}
	price_list = frappe.db.get_value("BOM", bom_name, "buying_price_list")
	if price_list and not frappe.db.exists("Price List", price_list):
		# Dead metadata: this site holds no Price List records at all and costs
		# at Valuation Rate. Harmless until something copies the BOM, at which
		# point the copy will not save and the error names the price list.
		values["buying_price_list"] = None
	if farm and not frappe.db.get_value("BOM", bom_name, "custom_farm"):
		values["custom_farm"] = farm

	for field, value in values.items():
		if frappe.db.has_column("BOM", field):
			frappe.db.set_value("BOM", bom_name, field, value, update_modified=False)
	if frappe.db.get_value("Item", item, "default_bom") != bom_name:
		frappe.db.set_value("Item", item, "default_bom", bom_name, update_modified=False)
	frappe.db.set_value("Herds", herd, "bom", bom_name)
	return bom_name


def _build(item, lines, herd, farm, template=None):
	"""A fresh submitted BOM for `item` to `lines`.

	Copied from the herd's previous ration when there is one, so the recipe
	UOMs travel with it: hay is written in kilograms and stocked in bales, and
	an item added without borrowing the old row's UOM would be read as bales —
	fourteen times the feed, and plausible enough to miss.
	"""
	old_row_by_item = {row.item_code: row for row in (template.items if template else [])}

	doc = frappe.copy_doc(template) if template else frappe.new_doc("BOM")
	if template:
		_carry_forward(doc, herd)
	doc.item = item
	doc.quantity = per_head_kg(lines)
	doc.is_active = 1
	doc.is_default = 1
	doc.with_operations = 0
	doc.custom_herd = herd
	doc.custom_is_livestock_feed = 1
	doc.custom_ration_kind = STANDING
	if farm and doc.meta.has_field("custom_farm") and not doc.get("custom_farm"):
		doc.custom_farm = farm
	if not doc.get("company"):
		doc.company = frappe.db.get_single_value("Livestock Settings", "custom_default_company")

	doc.set("items", [])
	for row in lines:
		item_doc = frappe.get_cached_doc("Item", row["item_code"])
		old = old_row_by_item.get(row["item_code"])
		doc.append("items", {
			"item_code": row["item_code"],
			"item_name": item_doc.item_name,
			"qty": row["qty"],
			"uom": old.uom if old else item_doc.stock_uom,
			"stock_uom": item_doc.stock_uom,
			"conversion_factor": old.conversion_factor if old else 1,
		})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def set_standing_ration(herd, lines, ration_item=None, farm=None):
	"""Make `lines` the herd's standing ration. Returns what changed.

	Idempotent by construction: submitting the ration a herd already has
	returns it untouched rather than minting a revision that says the same
	thing. A farm correcting the same way every morning would otherwise
	accumulate a BOM a day, which is what this site's BOM list already looks
	like.
	"""
	lines = _clean(lines)
	if not lines:
		frappe.throw(_("A ration needs at least one ingredient."))

	previous = frappe.db.get_value("Herds", herd, "bom")
	item = ration_item or (frappe.db.get_value("BOM", previous, "item") if previous else None)
	if not item:
		frappe.throw(
			_("Say which product this herd's ration is. A ration is a recipe FOR "
			  "something, and naming a new feed product is the farm's call.")
		)
	if not frappe.db.exists("Item", item):
		frappe.throw(_("{0} is not an item on this site.").format(item))

	quantity = per_head_kg(lines)
	if quantity <= 0:
		frappe.throw(_("A ration has to weigh something."))

	farm = farm or _farm_for(previous)
	signature = _signature(lines)

	if previous and frappe.db.get_value("BOM", previous, "item") == item:
		rows = frappe.get_all("BOM Item", filters={"parent": previous},
		                      fields=["item_code", "qty"])
		same_lines = _signature(
			[{"item_code": r.item_code, "qty": r.qty} for r in rows]) == signature
		if same_lines and abs(flt(frappe.db.get_value("BOM", previous, "quantity"))
		                      - quantity) < 0.0005:
			_adopt(previous, herd, farm)
			return {"bom": previous, "changed": False, "superseded": None,
			        "per_head_kg": quantity, "item": item}

	found = _matching(item, signature, quantity)
	if found:
		_adopt(found, herd, farm)
		return {"bom": found, "changed": found != previous, "superseded": previous,
		        "per_head_kg": quantity, "item": item}

	template = None
	if previous and frappe.db.get_value("BOM", previous, "item") == item:
		template = frappe.get_doc("BOM", previous)
	name = _build(item, lines, herd, farm, template)
	_adopt(name, herd, farm)
	return {"bom": name, "changed": True, "superseded": previous,
	        "per_head_kg": quantity, "item": item}


def _farm_for(previous):
	"""custom_farm is mandatory on BOM here. Taken from the ration being
	replaced, or from the store the feed comes out of, rather than hardcoded."""
	if previous:
		farm = frappe.db.get_value("BOM", previous, "custom_farm")
		if farm:
			return farm
	store = frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse")
	return frappe.db.get_value("Warehouse", store, "custom_farm") if store else None
