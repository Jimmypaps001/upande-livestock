# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Per-head additive doses: 7 g of Diamond V, 60 ml of Meat Grow, per head.

Mutara's ration sheet writes its additives as a dose per animal, beside the
kilos and outside the 100% the kilos add up to. Writing 7 g as "0.007 kg" in a
kilogram recipe loses the fact the farm actually works to and invites a typo
of a factor of a thousand; writing it as "7" in a kilogram recipe feeds seven
kilos of yeast. So a dose stays a dose:

* On the BOM it is a row whose RECIPE unit is Gram or Millilitre, `qty` the
  dose per head, and `conversion_factor` the item's stock units per gram or
  millilitre. ERPNext then computes `stock_qty` itself, and everything that
  moves stock (the Work Order's required items, the transfer, the
  consumption) is already in the stock unit — the same mechanism that has
  always carried hay written in kilograms and stocked in bales.
* It is NOT part of the ration's weight. A ration's `BOM.quantity` is the sum
  of its kilogram lines (`kg_total`), so the 100% and the per-head kilos mean
  what the farm means by them, and a 60 ml line cannot be added to kilos.
* Nutrition leaves it out (an additive's few grams carry no dry matter worth
  weighing, and a millilitre has no weight without a density nobody records).

Which rows are doses is decided by their unit, here, once (`is_dose`).

The conversion factor is the item's own UOM Conversion Detail when it has one
(a supplier pack, say), then ERPNext's UOM Conversion Factor table, then the
SI relationship between the units — which is physics, not a business number.
"""

from frappe.utils import flt

GRAM = "Gram"
MILLILITRE = "Millilitre"

#: The units a dose may be written in. Anything else is a kilogram line (or a
#: recipe unit such as hay's Kilogram-of-a-bale, which is not a dose either).
DOSE_UOMS = (GRAM, MILLILITRE)

#: Unit name -> (dimension, how many of the base unit one of it is). The base
#: of mass is the gram, of volume the millilitre. Spelled the ways this bench
#: spells them: ERPNext's setup data says "Kg", sites here say "Kilogram".
_SI = {
	"gram": ("mass", 1.0),
	"g": ("mass", 1.0),
	"kilogram": ("mass", 1000.0),
	"kg": ("mass", 1000.0),
	"milligram": ("mass", 0.001),
	"mg": ("mass", 0.001),
	"tonne": ("mass", 1_000_000.0),
	"millilitre": ("volume", 1.0),
	"milliliter": ("volume", 1.0),
	"ml": ("volume", 1.0),
	"litre": ("volume", 1000.0),
	"liter": ("volume", 1000.0),
	"l": ("volume", 1000.0),
}


def is_dose(uom):
	"""Is a recipe row in this unit a per-head dose rather than kilos?"""
	return (uom or "") in DOSE_UOMS


def si_factor(from_uom, to_uom):
	"""Stock units per one `from_uom`, from the units alone, or None.

	7 Gram of an item stocked in Kilogram is 7 x 0.001 kg. None when the two
	are not the same kind of quantity (grams of something stocked in litres,
	or in bags): only the item's own conversion can answer that.
	"""
	if (from_uom or "") == (to_uom or ""):
		return 1.0
	a = _SI.get((from_uom or "").strip().lower())
	b = _SI.get((to_uom or "").strip().lower())
	if not a or not b or a[0] != b[0]:
		return None
	return a[1] / b[1]


def dose_factor(item_code, dose_uom, stock_uom, item_factor=None, erpnext_factor=None):
	"""Stock units per one `dose_uom` of this item, or None when nothing knows.

	`item_factor` and `erpnext_factor` are looked up by the caller (see
	`conversion_factor`) so this stays pure and the precedence is testable:
	the item's own table first, ERPNext's general table next, the units last.
	"""
	for factor in (item_factor, erpnext_factor):
		if flt(factor) > 0:
			return flt(factor)
	return si_factor(dose_uom, stock_uom)


def conversion_factor(item_code, dose_uom):
	"""`dose_factor` for a real item, reading the site's own tables."""
	import frappe

	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
	item_factor = frappe.db.get_value(
		"UOM Conversion Detail",
		{"parent": item_code, "parenttype": "Item", "uom": dose_uom},
		"conversion_factor",
	)
	erpnext_factor = None
	if not item_factor and stock_uom and stock_uom != dose_uom:
		try:
			from erpnext.stock.doctype.item.item import get_uom_conv_factor

			erpnext_factor = get_uom_conv_factor(dose_uom, stock_uom)
		except Exception:
			erpnext_factor = None
	factor = dose_factor(item_code, dose_uom, stock_uom, item_factor, erpnext_factor)
	if not factor:
		frappe.throw(
			frappe._(
				"{0} is stocked in {1}, and nothing says how many {1} one {2} is. Add {2} to "
				"the item's UOM conversions, or enter it in kilos."
			).format(item_code, stock_uom or "?", dose_uom)
		)
	return factor


def dose_uom_of(row):
	"""The dose unit a recipe line names, or None for a kilogram line.

	Lines arrive as `{item_code, qty, dose_uom}` from the pages; `uom` is
	accepted too, so a line read back off a BOM can be sent straight back.
	"""
	uom = row.get("dose_uom") or row.get("uom")
	return uom if is_dose(uom) else None


def kg_total(lines, kilos_of=None):
	"""What a recipe weighs per head: its kilogram lines, doses left out.

	`kilos_of(row)` turns a line written in another unit (molasses in Litre,
	hay in bales) into its kilos — `_units.line_kilos`. Without it every line
	counts its quantity as kilos, as all lines did before units.
	"""
	weigh = kilos_of or (lambda row: flt(row.get("qty")))
	return sum(weigh(row) for row in lines or [] if not dose_uom_of(row))
