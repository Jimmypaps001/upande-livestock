"""What a feeding screen can offer for one herd: its standing ration, plus
every recipe tuned for it before.

The standing ration is read off `Herds.bom`, never off `custom_herd`. Two of
this site's BOMs are each the standing ration for two herds at once
(BOM-TMR Calves Meal-011 for both 0-2 and 2-4; BOM-Dry/Steamers/Incalf
Heifers-012 for both INCALF HEIFERS and STEAMERS) and `custom_herd` names only
one of the pair — see the backfill patch's own docstring for why a single
Link field cannot hold both. `Herds.bom` is the one place that answers "what
is this herd's standing ration" for every herd, shared BOM or not, so that is
what this endpoint reads; a `custom_herd`-only query would come back empty for
whichever herd of the pair `custom_herd` does not name.

Tuned recipes are the reverse: they exist only via `custom_herd`, since a
tuned BOM is never a herd's `Herds.bom`.
"""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import guard_read, run


def _lines(bom_no):
	"""A recipe's lines in RECIPE qty/uom — `BOM Item.qty`/`uom`, never
	`stock_qty`/`stock_uom`. Hay (4040010034) is written as 2-5 kg on every
	standing BOM checked (Lactating Group 1, TMR Calves Meal, Dry/Steamers/
	Incalf Heifers) but stocked in BALE at a conversion factor of 0.07 —
	returning stock units here would hand a picker a number ~14x too small."""
	return [
		{
			"item_code": row.item_code,
			"item_name": row.item_name or row.item_code,
			"qty": frappe.utils.flt(row.qty),
			"uom": row.uom,
		}
		for row in frappe.get_all(
			"BOM Item",
			filters={"parent": bom_no},
			fields=["item_code", "item_name", "qty", "uom"],
			order_by="idx asc",
		)
	]


def _recipe(bom_no, kind, is_standing):
	bom = frappe.db.get_value(
		"BOM", bom_no, ["item", "item_name", "quantity", "uom", "creation"], as_dict=True
	)
	return {
		"bom_no": bom_no,
		"item_code": bom.item,
		"item_name": bom.item_name or bom.item,
		"kind": kind,
		"is_standing": is_standing,
		"created": bom.creation,
		"per_head_qty": frappe.utils.flt(bom.quantity),
		"uom": bom.uom,
		"lines": _lines(bom_no),
	}


@frappe.whitelist()
def herd_recipes(herd):
	"""A herd's recipes: the standing ration (from `Herds.bom`) first, then
	every tuned BOM made for this herd (`custom_herd = herd`,
	`custom_ration_kind = "Tuned"`), newest first — the one most likely to be
	what was fed yesterday belongs closest to the standing ration, not buried
	under a year of one-off tunes."""

	def go():
		guard_read("Herds")
		if not herd:
			frappe.throw(_("Choose a herd."))

		standing_bom = frappe.db.get_value("Herds", herd, "bom")
		if not standing_bom:
			frappe.throw(_("Herd {0} has no BOM linked.").format(herd))

		recipes = [_recipe(standing_bom, "Standing", True)]

		tuned = frappe.get_all(
			"BOM",
			filters={
				"custom_herd": herd,
				"custom_ration_kind": "Tuned",
				"docstatus": 1,
			},
			fields=["name"],
			order_by="creation desc",
		)
		recipes.extend(
			_recipe(row.name, "Tuned", False) for row in tuned if row.name != standing_bom
		)

		return {"ok": True, "herd": herd, "standing_bom": standing_bom, "recipes": recipes}

	return run(go, "livestock herd_recipes failed")
