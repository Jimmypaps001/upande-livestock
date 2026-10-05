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



EVENT_TYPE = "Livestock Event Type"
GROUPS_TABLE = "Livestock Event Type Item Group"


def _rules():
	"""Each event type's stock rule, keyed by event type.

	{type: {"posts": bool, "groups": [..], "default_store": str|None,
	        "must_name_item": bool}}

	The rule lives on the Livestock Event Type itself — Posts Stock Entry, its
	Item Groups, a Default Store, Must Name an Item — edited there or on the
	Settings screen's Stock tab. It replaced a Settings table of one row per
	(event, group), which repeated the event for every group it drew on, and
	the scattered drug/semen group and store settings beside it.

	Read defensively: a site running this code before its migrate has none of
	these columns, and an event form must not go down for it.
	"""
	try:
		meta = frappe.get_meta(EVENT_TYPE)
		if not meta.has_field("posts_stock_entry"):
			return {}
		rows = frappe.get_all(
			EVENT_TYPE,
			filters={"posts_stock_entry": 1},
			fields=["name", "default_store", "must_name_item"],
		)
		groups = {}
		for g in frappe.get_all(
			GROUPS_TABLE,
			filters={"parenttype": EVENT_TYPE, "parentfield": "stock_item_groups"},
			fields=["parent", "item_group"],
			order_by="idx asc",
		):
			groups.setdefault(g.parent, []).append(g.item_group)
	except Exception:
		return {}
	return {
		r.name: {
			"posts": True,
			"groups": list(dict.fromkeys(g for g in groups.get(r.name, []) if g)),
			"default_store": r.default_store or None,
			"must_name_item": bool(r.must_name_item),
		}
		for r in rows
	}


def _mapping_rows():
	"""Every (event_type, item_group) pair the rules allow.

	The shape the old Settings table had, kept so `groups_for_event` and every
	test that pins the mapping read it the same way.
	"""
	return [
		{"event_type": t, "item_group": g}
		for t, rule in _rules().items()
		for g in rule["groups"]
	]


def groups_for_event(event_type):
	"""The item groups this event type draws on, in order, deduplicated."""
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


def has_mapping():
	"""Has any event type been set to post stock?"""
	return bool(_mapping_rows())


def consumes_items(event_type):
	"""Whether this event type posts stock: ticked, and drawing on some group."""
	return bool(groups_for_event(event_type))


def default_store(event_type):
	"""The store this event type issues from when a line names none."""
	return (_rules().get(event_type) or {}).get("default_store")


def must_name_item(event_type):
	"""Whether an event of this type must say what it used."""
	return bool((_rules().get(event_type) or {}).get("must_name_item"))


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

	preferred = default_store(event_type)
	out = []
	for item_code, entry in held.items():
		# The event type's default store first when it holds the item, then the
		# most-stocked, so `locations[0]` is the store to go to and a short line
		# has somewhere obvious to try next.
		entry["locations"].sort(
			key=lambda loc: (loc["warehouse"] != preferred, -loc["qty"], loc["warehouse"])
		)
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
