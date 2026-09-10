# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A recipe's ingredients, in the units the recipe is written in.

`BOM Item.qty` / `.uom`, never `stock_qty` / `stock_uom`. Hay (4040010034) is
written as 5 kg on every standing BOM on this site but stocked in BALE at a
conversion factor of 0.07, so its `stock_qty` is 0.35. Handing an operator
"0.35 BALE" where the recipe says "5 Kilogram" is not a different unit for the
same fact — it is a fourteenth of the hay, in a number they cannot check
against the mixer.

Fetched for a whole set of BOMs in one query. Both callers deal in lists —
`herd_recipes` returns every recipe a herd has ever been fed, `ration_history`
up to a thousand rows — and a per-BOM fetch inside either loop is one query per
row on a page that already reads 5,000 Work Orders.
"""

import frappe
from frappe.utils import flt


def lines_for(bom_nos):
	"""{bom_no: [line, ...]} for every BOM named, in recipe qty/uom.

	One query for the whole set, whatever its size. A BOM with no rows is
	simply absent from the result, so callers read it with `.get(bom, [])`.
	"""
	wanted = sorted({name for name in (bom_nos or []) if name})
	if not wanted:
		return {}

	out = {}
	for row in frappe.get_all(
		"BOM Item",
		filters={"parent": ["in", wanted], "parenttype": "BOM"},
		fields=["parent", "item_code", "item_name", "qty", "uom", "idx"],
		order_by="parent asc, idx asc",
	):
		out.setdefault(row.parent, []).append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name or row.item_code,
				"qty": flt(row.qty),
				"uom": row.uom,
			}
		)
	return out


def lines(bom_no):
	"""One recipe's lines, the same shape `lines_for` returns."""
	return lines_for([bom_no]).get(bom_no, [])
