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


def _was_fed_to(herd, bom_no):
	"""Has this herd actually been mixed this recipe? The Work Order says so.

	The authoritative record of what a herd was really fed — the same source
	`ration_history` reports from and `herd_recipes` offers from. It has to be
	a route into this check because the `custom_herd` stamp never covered it:
	only the six standing rations were ever stamped, so every recipe this farm
	fed before the stamps existed would otherwise be refused here the moment a
	picker offered it.
	"""
	return bool(
		frappe.db.exists("Work Order", {"custom_herd": herd, "bom_no": bom_no, "docstatus": 1})
	)


def _base_for(herd, base_bom):
	"""The BOM to copy from: the herd's own standing ration when `base_bom`
	is not given (today's behaviour, unchanged), or `base_bom` itself once
	proven to actually belong to this herd.

	"Belongs to this herd" means: it *is* the herd's standing BOM, its
	`custom_herd` names this herd, or this herd has been fed it — the same
	three ways `herd_recipes` builds a herd's recipe list, so nothing can be
	tuned into a herd's feed that the picker could not itself have offered,
	and nothing the picker offers is refused here. Anything else is refused
	outright; a caller must not be able to walk an arbitrary BOM from
	elsewhere on the site into this herd's feed by naming it directly.
	"""
	standing_name = frappe.db.get_value("Herds", herd, "bom")
	if not standing_name:
		frappe.throw(_("Herd {0} has no BOM linked.").format(herd))
	if not base_bom:
		return frappe.get_doc("BOM", standing_name)

	base = frappe.get_doc("BOM", base_bom)
	if base.docstatus != 1:
		frappe.throw(_("BOM {0} is not a submitted BOM.").format(base_bom))
	standing_item = frappe.db.get_value("BOM", standing_name, "item")
	if base.item != standing_item:
		frappe.throw(
			_("BOM {0} is not a recipe for {1}'s ration item.").format(base_bom, herd)
		)
	if (
		base.name != standing_name
		and base.custom_herd != herd
		and not _was_fed_to(herd, base.name)
	):
		frappe.throw(_("BOM {0} does not belong to herd {1}.").format(base_bom, herd))
	return base


def _carry_forward(doc, herd):
	"""Make a copy of an OLD recipe insertable, without changing its recipe.

	A BOM that has sat untouched for months is not necessarily a BOM that will
	save. Nothing revalidates it until something copies it, and the picker now
	offers recipes going back to March. Two things on this site were waiting
	there, both found by tuning from BOM-Dry/Steamers/Incalf Heifers-004:

	`buying_price_list` — every BOM made before 2026-05 carries "Standard
	Buying" while the site holds no Price List records at all, so the insert
	dies with "Could not find Price List: Standard Buying". Dead metadata from
	whatever imported them: these BOMs cost at `rm_cost_as_per = Valuation
	Rate` and never consult it. Dropped only when it genuinely does not
	resolve, so a site that does keep price lists is untouched.

	`custom_farm` — a mandatory Link (SCP's, on BOM) that 2,565 of this site's
	BOMs predate and leave blank, so the insert dies with MandatoryError. The
	herd's own standing ration knows the answer (Kapkolia, for every herd
	here), and a recipe tuned for this herd is mixed on the same farm the herd
	is fed on, so it is carried forward from there rather than guessed.

	Neither touches an ingredient or a quantity. If the base BOM already
	answers, its answer stands.
	"""
	if doc.buying_price_list and not frappe.db.exists("Price List", doc.buying_price_list):
		doc.buying_price_list = None
	if doc.meta.has_field("custom_farm") and not doc.get("custom_farm"):
		standing_name = frappe.db.get_value("Herds", herd, "bom")
		farm = frappe.db.get_value("BOM", standing_name, "custom_farm") if standing_name else None
		if farm:
			doc.custom_farm = farm


def tuned_bom(herd, lines, base_bom=None):
	"""Return a BOM name that makes the herd's feed item to `lines`.

	Returns the base BOM unchanged when the tune matches it — a screen that
	submits without editing anything should not mint a duplicate. The base is
	the herd's own standing ration (`Herds.bom`) unless `base_bom` names a
	recipe previously used for this herd, in which case tuning starts from
	that recipe instead — see `_base_for`.
	"""
	lines = _clean(lines)
	if not lines:
		frappe.throw(_("A feed run needs at least one ingredient."))

	base = _base_for(herd, base_bom)

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
	_carry_forward(doc, herd)
	doc.is_active = 1  # ERPNext refuses a Work Order against anything else
	doc.is_default = 0
	# The back-link to the herd this ration was made for, so a BOM's
	# provenance lives with the recipe rather than being inferred. See
	# fixtures/custom_field.json for the three custom_* fields on BOM.
	doc.custom_herd = herd
	doc.custom_is_livestock_feed = 1
	doc.custom_ration_kind = "Tuned"
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
