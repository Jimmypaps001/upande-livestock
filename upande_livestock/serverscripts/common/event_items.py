"""What an event may consume, and where it is.

`stock_items` knew two kinds, "drug" and "semen", each resolving to a single
item group through a constant in the source — so a vaccination needing a
syringe out of `Consumables Purchased` could not have one, and a Calving that
uses gloves and a bolus had nowhere to record either.

It also took the store from a list somebody typed into Livestock Settings,
which failed twice in one day: that list was empty on live while
`drug_warehouse` named a warehouse with zero stocked bins, so the drug picker
returned nothing on three screens while 74 stocked drug bins sat in six other
stores. The item already knows where it is — `locations`, most-stocked first —
so asking a person to configure it as well was a second source of truth, and
the two disagreed.

So: the groups come from the farm's mapping, as many per event as it needs, and
the warehouses are every leaf warehouse of the event's company.

COMPANY SCOPING IS LOAD-BEARING, not decoration. This bench carries 761 leaf
warehouses across six companies. The configured store list was what
accidentally kept Kaitet Ltd's 263 of them off a Karen Roses event; with it
gone, company is the only guard, and an unscoped search would offer stock
ERPNext refuses to issue.

Balances are still never summed across stores: 16 in one and 4 in another is
not 20 anywhere, and an issue drawn on 20 fails at the shelf.
"""

import frappe
from frappe.utils import flt

SETTINGS = "Livestock Settings"
TABLE = "custom_event_item_groups"


def _mapping_rows():
	"""Every (event_type, item_group) row, in grid order.

	Asked for by name rather than read off the Single: a site running this code
	before its migrate has no such table, and reading it raises rather than
	returning nothing. A deploy that lands before its migrate must fall back,
	not take every event form down.
	"""
	try:
		if not frappe.get_meta(SETTINGS).has_field(TABLE):
			return []
		return frappe.get_all(
			"Livestock Event Item Group",
			filters={"parenttype": SETTINGS, "parentfield": TABLE},
			fields=["event_type", "item_group"],
			order_by="idx asc",
		)
	except Exception:
		return []


def groups_for_event(event_type):
	"""The item groups this event type draws on, in grid order, deduplicated.

	Two rows naming the same group is a typo, not a doubling — the union is
	what the picker wants either way.
	"""
	if not event_type:
		return []
	out = []
	for row in _mapping_rows():
		if row.get("event_type") != event_type:
			continue
		group = row.get("item_group")
		if group and group not in out:
			out.append(group)
	return out


def consumes_items(event_type):
	"""Whether this event type consumes anything at all.

	Replaces the `consumes_drugs` checkbox: what an event may consume stopped
	being a flag a developer sets and became a list the farm writes.
	"""
	return bool(groups_for_event(event_type))


def _default_company():
	# common.company.default_company: the setting, then the user's and the
	# site's default. The raw setting alone left a site without it with none.
	from upande_livestock.serverscripts.common.company import default_company

	try:
		return default_company()
	except Exception:
		return None


def _company_warehouses(company):
	"""Every leaf warehouse belonging to `company`.

	Leaf only: a group warehouse holds no stock and an issue from one is
	refused. Disabled ones are left out for the same reason.
	"""
	if not company:
		return []
	try:
		return frappe.get_all(
			"Warehouse",
			filters={"company": company, "is_group": 0, "disabled": 0},
			pluck="name",
			order_by="name asc",
		)
	except Exception:
		return []


def _balances(groups, warehouses):
	"""One row per (item, warehouse) with a positive balance."""
	if not groups or not warehouses:
		return []
	return frappe.db.sql(
		"""SELECT i.name, i.item_name, i.stock_uom, b.warehouse, b.actual_qty AS qty
		   FROM `tabItem` i
		   JOIN `tabBin` b ON b.item_code = i.name
		   WHERE i.item_group IN %(groups)s
		     AND b.warehouse IN %(warehouses)s
		     AND b.actual_qty > 0
		     AND IFNULL(i.disabled, 0) = 0
		     AND IFNULL(i.is_stock_item, 1) = 1
		   ORDER BY i.item_name ASC
		   LIMIT 2000""",
		{"groups": groups, "warehouses": warehouses},
		as_dict=True,
	)


def items_for_event(event_type, company=None):
	"""Items this event may consume, restricted to what is actually in stock.

	One choice per ITEM, not per shelf: the form picks an item and the store
	rides along, on `warehouse` (where most of it is) and `locations` (every
	store holding any, most first). Shaped exactly as `stock_items` returned,
	so a caller switching over changes one line.
	"""
	groups = groups_for_event(event_type)
	if not groups:
		return []
	warehouses = _company_warehouses(company or _default_company())
	if not warehouses:
		return []

	held = {}
	for r in _balances(groups, warehouses):
		entry = held.setdefault(
			r["name"],
			{"item_name": r.get("item_name") or r["name"], "uom": r.get("stock_uom"), "locations": []},
		)
		entry["locations"].append({"warehouse": r["warehouse"], "qty": flt(r["qty"])})

	out = []
	for item_code, entry in held.items():
		# Most-stocked first, so `locations[0]` is the store to go to and a short
		# line has somewhere obvious to try next.
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
