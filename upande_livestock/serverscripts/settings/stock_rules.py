# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Settings screen's Stock tab: every event type's stock rule in one place.

Each rule lives on its Livestock Event Type — Posts Stock Entry, Item Groups,
Default Store, Must Name an Item — because a multi-select of item groups cannot
sit inside a Settings child-table row. This lists them together and saves them
back, so the farm sets what every event posts on one screen rather than opening
each event type.

Read-guarded on Livestock Settings like the rest of the page; saving needs
write on Livestock Event Type.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run

EVENT_TYPE = "Livestock Event Type"


def rule_rows():
	types = frappe.get_all(
		EVENT_TYPE,
		filters={"is_active": 1},
		fields=["name", "posts_stock_entry", "default_store", "must_name_item"],
		order_by="name asc",
	)
	groups = {}
	for g in frappe.get_all(
		"Livestock Event Type Item Group",
		filters={"parenttype": EVENT_TYPE, "parentfield": "stock_item_groups"},
		fields=["parent", "item_group"],
		order_by="idx asc",
	):
		groups.setdefault(g.parent, []).append(g.item_group)
	return [
		{
			"event_type": t.name,
			"posts_stock_entry": bool(t.posts_stock_entry),
			"item_groups": groups.get(t.name, []),
			"default_store": t.default_store or None,
			"must_name_item": bool(t.must_name_item),
		}
		for t in types
	]


@frappe.whitelist()
def stock_rules():
	"""Every active event type's rule, and the choices the controls offer."""

	def go():
		guard_read("Livestock Settings")
		return {
			"ok": True,
			"rules": rule_rows(),
			"item_groups": frappe.get_all(
				"Item Group", filters={"is_group": 0}, pluck="name", order_by="name asc"
			),
			"stores": frappe.get_all(
				"Warehouse", filters={"is_group": 0, "disabled": 0}, pluck="name", order_by="name asc"
			),
		}

	return run(go, "livestock stock_rules failed")
