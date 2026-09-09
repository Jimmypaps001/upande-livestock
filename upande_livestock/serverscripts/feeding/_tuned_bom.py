"""Turn a hand-tuned recipe into something ERPNext will manufacture.

There is no shorter route. Two were tried on this site and both fail:

  * A Work Order against an inactive BOM is refused outright —
    "BOM ... must be active".
  * Hand-editing ``Work Order.required_items[].required_qty`` does not survive
    the save. ``Work Order.validate`` calls ``set_required_items(reset_only_qty=…)``
    and puts the BOM's numbers back. Set 300 to 1299, save, read 300.

So a tuned recipe has to be a real, active, submitted BOM. What it must NOT be
is the herd's default: ``is_default = 0`` keeps it out of every herd picker and
leaves ``Item.default_bom`` and ``Herds.bom`` pointing where they did.

Identical tunes are reused. A farm correcting the same way every morning would
otherwise accumulate a BOM a day, and the BOM list on the live site is already
fifteen revisions deep on one item.
"""

import frappe
from frappe import _
from frappe.utils import flt


def _signature(lines):
	"""A stable key for a set of (item, qty) pairs, order-independent."""
	return tuple(sorted((row["item_code"], round(flt(row["qty"]), 4)) for row in lines))


def _clean(lines):
	"""Drop empty/zero rows and merge duplicate item_codes by summing their
	qty — a caller submitting the same ingredient twice (e.g. added once by
	hand and once by a recipe default) means "this much in total", not two
	separate BOM Item rows for the same item."""
	totals = {}
	order = []
	for row in lines or []:
		item = (row.get("item_code") or "").strip()
		qty = flt(row.get("qty"))
		if not item or qty <= 0:
			continue
		if item not in totals:
			order.append(item)
			totals[item] = 0.0
		totals[item] += qty
	return [{"item_code": item, "qty": totals[item]} for item in order]


def _existing_match(item, signature):
	"""A submitted non-default BOM for `item` whose lines match, or None."""
	for row in frappe.get_all(
		"BOM",
		filters={"item": item, "docstatus": 1, "is_default": 0, "is_active": 1},
		fields=["name"],
		order_by="creation desc",
	):
		lines = frappe.get_all(
			"BOM Item", filters={"parent": row.name}, fields=["item_code", "qty"]
		)
		if _signature([{"item_code": r.item_code, "qty": r.qty} for r in lines]) == signature:
			return row.name
	return None


def tuned_bom(herd, lines):
	"""Return a BOM name that makes the herd's feed item to `lines`.

	Returns the herd's own BOM unchanged when the tune matches it — a screen
	that submits without editing anything should not mint a duplicate.
	"""
	lines = _clean(lines)
	if not lines:
		frappe.throw(_("A feed run needs at least one ingredient."))

	base_name = frappe.db.get_value("Herds", herd, "bom")
	if not base_name:
		frappe.throw(_("Herd {0} has no BOM linked.").format(herd))
	base = frappe.get_doc("BOM", base_name)

	signature = _signature(lines)
	if _signature([{"item_code": r.item_code, "qty": r.qty} for r in base.items]) == signature:
		return base.name

	found = _existing_match(base.item, signature)
	if found:
		return found

	# The caller's qty is in whatever UOM the *recipe* uses for that item, not
	# necessarily the item's stock UOM (hay on this site is written as kg in
	# the recipe but stocked in BALE, cf 0.07 bale/kg). Reuse the base BOM's
	# own uom/conversion_factor for any item the base BOM already carries, so
	# ERPNext derives the same stock_qty it always would. Only an item the
	# operator adds that the base BOM has never heard of falls back to the
	# item's stock UOM at a factor of 1 — there is no recipe UOM to borrow.
	base_row_by_item = {row.item_code: row for row in base.items}

	doc = frappe.copy_doc(base)
	doc.is_active = 1  # ERPNext refuses a Work Order against anything else
	doc.is_default = 0
	doc.set("items", [])
	for row in lines:
		item = frappe.get_cached_doc("Item", row["item_code"])
		base_row = base_row_by_item.get(row["item_code"])
		if base_row:
			uom = base_row.uom
			conversion_factor = base_row.conversion_factor
		else:
			uom = item.stock_uom
			conversion_factor = 1
		doc.append(
			"items",
			{
				"item_code": row["item_code"],
				"item_name": item.item_name,
				"qty": row["qty"],
				"uom": uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": conversion_factor,
			},
		)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name
