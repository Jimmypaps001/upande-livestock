"""What a livestock form may offer to issue from the store, and where it is.

Drug and semen pickers must not simply list every Item in the drug item group —
most of a 600-item group is not something the store actually holds, and offering
it invites an issue that then fails. `stock_items` scopes the list to items with
real, warehouse-scoped, on-hand quantity instead.

## Two things this used to hard-code, and both were wrong on live

THE ITEM GROUP. It asked for "DRUGS", which is what kaitet.local calls its drug
catalogue (606 items). The live site calls it `Dairy Drugs` (215 items) and
keeps a near-empty `Drugs` parent node with 12. The semen group "DAIRY" has no
items on live at all. So both pickers came back empty on the site that matters
and full on the one that did not. A farm names its own item groups; the group
is a setting now, defaulting to the old constants so nothing here changes.

THE STORE. One warehouse was searched — `Livestock Settings.drug_warehouse` —
and on live it names a store created 2026-08-26 with **zero Bin rows**. The
drugs are in the stores the farm actually uses. Every configured drug store is
searched now (`stock.drug_source_warehouses`), the same way feeding has always
searched its feed stores.

## Each choice says where to find it

Balances are still never summed across stores: `qty` is what is in the one
warehouse named, because a summed balance promises stock the issue cannot find
— 33 units in a packaging store on the other side of the farm is not 33 units
here. The warehouse named is the one holding the most, so the line is issued
from a shelf that can supply it, and `locations` lists every store that has
any, so the operator can go to a different one when the first runs short.
"""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common import stock as livestock_stock

#: What the older sites in this group call these groups. Kept as the default so
#: a site that never fills the setting in behaves exactly as it did before.
DEFAULT_ITEM_GROUP = {"drug": "DRUGS", "semen": "DAIRY"}
SETTING = {"drug": "custom_drug_item_group", "semen": "custom_semen_item_group"}


def item_group_for(kind):
	"""The item group this farm keeps `kind` in, or the old constant."""
	try:
		configured = frappe.db.get_single_value("Livestock Settings", SETTING[kind])
	except Exception:
		configured = None
	return configured or DEFAULT_ITEM_GROUP[kind]


def _balances(group, warehouses, name_filter):
	"""One row per (item, warehouse) with a positive balance."""
	if not warehouses:
		return []
	placeholders = ", ".join(["%s"] * len(warehouses))
	return frappe.db.sql(
		f"""SELECT i.name, i.item_name, i.stock_uom, b.warehouse, b.actual_qty AS qty
		    FROM `tabItem` i
		    JOIN `tabBin` b ON b.item_code = i.name
		    WHERE i.item_group = %s
		      AND b.warehouse IN ({placeholders})
		      AND b.actual_qty > 0
		      AND IFNULL(i.disabled, 0) = 0
		      AND IFNULL(i.is_stock_item, 1) = 1
		      {name_filter}
		    ORDER BY i.item_name ASC
		    LIMIT 2000""",
		[group, *warehouses],
		as_dict=True,
	)


def stock_items(kind, warehouse=None):
	"""Items a livestock form can issue, restricted to what is actually in stock.

	`kind` is "drug" or "semen". One choice per ITEM, not per shelf — the
	picker picks a drug and the warehouse rides along with it, on `warehouse`
	(where most of it is) and `locations` (every store holding any).

	`warehouse` narrows to a single store, for the picker that reloads when the
	operator changes stores. Left unset, every configured drug store is
	searched.
	"""
	group = item_group_for(kind)
	name_filter = (
		"" if kind == "drug" else "AND LOWER(CONCAT(i.name, ' ', IFNULL(i.item_name, ''))) LIKE '%%semen%%'"
	)
	warehouses = [warehouse] if warehouse else livestock_stock.drug_source_warehouses()

	held = {}
	for r in _balances(group, warehouses, name_filter):
		entry = held.setdefault(
			r.name,
			{"item_name": r.item_name or r.name, "uom": r.stock_uom, "locations": []},
		)
		entry["locations"].append({"warehouse": r.warehouse, "qty": flt(r.qty)})

	out = []
	for item_code, entry in held.items():
		# Most-stocked first, so `locations[0]` is the store to go to and a
		# short line has somewhere obvious to try next.
		entry["locations"].sort(key=lambda loc: (-loc["qty"], loc["warehouse"]))
		best = entry["locations"][0]
		out.append(
			{
				"value": item_code,
				"label": "{0}  ·  {1:g} {2} in {3}".format(
					entry["item_name"], best["qty"], entry["uom"] or "", best["warehouse"]
				).replace("  ", " ").strip(),
				"item_name": entry["item_name"],
				"qty": best["qty"],
				"uom": entry["uom"],
				"warehouse": best["warehouse"],
				"locations": entry["locations"],
			}
		)
	out.sort(key=lambda i: (i["item_name"] or "").lower())
	return out
