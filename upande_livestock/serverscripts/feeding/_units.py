# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The units a feed line may be written in, and what each is in kilos.

The stores count some feeds in other units: molasses in Litre, hay in bales.
The recipe screens let a line be written in any unit the ITEM knows — its
stock unit and every row of its UOM Conversion Detail — and show the kilo
equivalent beside it, because rations are balanced and costed by weight.

"KG" HAS TWO NAMES. ERPNext's setup data ships the unit as "Kg"; sites here
created "Kilogram". Both are kilograms everywhere in this app (`is_kg`), and a
new feed item is stocked in whichever this site has (`kilogram_uom`).

What "kilos per unit" means: one Litre of molasses at 1.4 kg a litre is 1.4.
It is read off the item's own conversion table: a row's `conversion_factor` is
stock units per one of that unit, so with a kilogram row in the table (stock
units per kilo) any unit converts through the stock unit. A stock unit that is
itself kilos needs no row; SI mass units (Gram, Tonne) convert by physics.
Nothing else is guessed: a unit with no route to kilos answers None and the
page says so rather than inventing a density.
"""

from frappe.utils import flt

from upande_livestock.serverscripts.feeding._doses import is_dose, si_factor

#: Every spelling of the kilogram this bench has met.
KG_NAMES = ("kg", "kilogram", "kgs", "kilograms")


def is_kg(uom):
	"""Is this unit the kilogram, whatever this site calls it?"""
	return (uom or "").strip().lower() in KG_NAMES


def kilos_per(uom, stock_uom, stock_per_uom=None, stock_per_kg=None):
	"""Kilograms in one `uom` of an item stocked in `stock_uom`, or None. Pure.

	`stock_per_uom` is the item's conversion factor for `uom` (stock units per
	one of it; 1 for the stock unit itself), `stock_per_kg` its factor for a
	kilogram row when it has one.
	"""
	if is_kg(uom):
		return 1.0
	mass = si_factor(uom, "Kilogram")
	if mass is not None:
		return mass
	per_uom = 1.0 if (uom or "") == (stock_uom or "") else flt(stock_per_uom)
	if per_uom <= 0:
		return None
	if is_kg(stock_uom):
		kg_per_stock = 1.0
	elif flt(stock_per_kg) > 0:
		kg_per_stock = 1.0 / flt(stock_per_kg)
	else:
		kg_per_stock = si_factor(stock_uom, "Kilogram")
	if not kg_per_stock:
		return None
	return per_uom * kg_per_stock


def unit_options(stock_uom, conversions):
	"""What a line of this item may be written in. Pure.

	`conversions` is [(uom, stock units per one)] from the item's table. The
	stock unit first, then the table, each once, with its kilos per unit
	(None where nothing says). A kilogram row is listed like any other.
	"""
	stock_per_kg = next((flt(f) for u, f in conversions if is_kg(u) and flt(f) > 0), None)
	out, seen = [], set()
	for uom, factor in [(stock_uom, 1.0)] + list(conversions):
		if not uom or uom in seen:
			continue
		seen.add(uom)
		out.append({
			"uom": uom,
			"factor": flt(factor) or None,
			"kg": kilos_per(uom, stock_uom, factor, stock_per_kg),
		})
	return out


def explicit_unit(row):
	"""The non-kilogram, non-dose unit a line names, or None for kilos."""
	uom = row.get("uom")
	if not uom or is_kg(uom) or is_dose(uom) or row.get("dose_uom"):
		return None
	return uom


def line_kilos(row, units):
	"""What a non-dose line weighs in kilos. Pure.

	`units` is `item_units` output. A line in kilos (or naming no unit) is its
	quantity; one in another unit is converted by the item's table; one that
	nothing converts keeps its quantity, as every line did before units.
	"""
	qty = flt(row.get("qty"))
	uom = explicit_unit(row)
	if not uom:
		return qty
	for opt in (units.get(row.get("item_code")) or {}).get("uoms", []):
		if opt["uom"] == uom and opt["kg"]:
			return qty * flt(opt["kg"])
	return qty


def item_units(item_codes):
	"""{item_code: {stock_uom, uoms: [{uom, factor, kg}]}} for real items."""
	import frappe

	codes = sorted({c for c in item_codes or [] if c})
	if not codes:
		return {}
	stock = dict(
		frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "stock_uom"], as_list=True)
	)
	conv = {}
	for r in frappe.get_all(
		"UOM Conversion Detail",
		filters={"parent": ["in", codes], "parenttype": "Item"},
		fields=["parent", "uom", "conversion_factor"],
		order_by="idx asc",
	):
		conv.setdefault(r.parent, []).append((r.uom, flt(r.conversion_factor)))
	return {
		code: {"stock_uom": stock[code], "uoms": unit_options(stock[code], conv.get(code, []))}
		for code in codes
		if code in stock
	}


def units_for_lines(lines):
	"""`item_units` for only the lines that name a unit other than kilos —
	so a recipe written in kilos, every recipe before units, costs no query."""
	codes = [r.get("item_code") for r in lines or [] if explicit_unit(r)]
	return item_units(codes) if codes else {}


def kilogram_uom():
	"""The kilogram UOM on this site: "Kilogram" where it exists, else "Kg"."""
	import frappe

	for name in ("Kilogram", "Kg", "kg"):
		if frappe.db.exists("UOM", name):
			return name
	return "Kg"
