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


def _existing_match(item, signature, quantity):
	"""A submitted non-default BOM for `item` whose lines AND batch size match.

	`quantity` is part of the identity, not decoration. `_engine` reads
	`per_head = flt(bom.quantity)` and scales the whole run by it, so two BOMs
	with byte-identical lines and quantities of 1 and 100 make runs that differ
	by a factor of a hundred. Matching on the lines alone would hand back the
	wrong one of those — silently, and only for a farm that happens to keep a
	batch-sized BOM for the same item, which is exactly what the BOM list on this
	site already looks like.
	"""
	for row in frappe.get_all(
		"BOM",
		filters={
			"item": item,
			"docstatus": 1,
			"is_default": 0,
			"is_active": 1,
			"quantity": flt(quantity),
		},
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

	# The tuned BOM is a copy of the base, so it inherits the base's batch size;
	# only a BOM with the SAME batch size is an equivalent of what we would build.
	found = _existing_match(base.item, signature, base.quantity)
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
	# ignore_permissions on both insert and submit: this BOM is machinery, not a
	# document the operator authors. It is minted on their behalf and they never
	# see it, and ERPNext offers no other route to a hand-tuned recipe — a Work
	# Order refuses an inactive BOM, and hand-edited required_items quantities
	# are reset on save (both proven empirically on this site; see the module
	# docstring). The authorization actually being exercised is "manufacture
	# feed and move stock", and that is checked one layer up, in manual_feed's
	# guard("Work Order") and guard("Stock Entry").
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name
