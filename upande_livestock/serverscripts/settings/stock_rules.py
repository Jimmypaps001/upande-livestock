# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Settings screen's Events section: every event type, whether the farm
records it, and — for one it does — what it draws from stock and how often it
comes round.

The switch is the event type's Enabled box (`is_active`; see
common/event_types). The stock rule lives on the event type too — Posts Stock
Entry, Item Groups, Default Store, Must Name an Item — because a multi-select
of item groups cannot sit inside a Settings child-table row. "How often" is the
Livestock Settings timings that govern the event (timings.EVENT_TIMINGS),
named here and edited through save_livestock_settings like any other setting,
so there is one stored value and one set of rules for it.

Every type is listed, switched off or not: a disabled one is how it is turned
back on. Read-guarded on Livestock Settings like the rest of the page; saving
needs write on Livestock Event Type.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.timings import EVENT_TIMINGS

EVENT_TYPE = "Livestock Event Type"


def _timings(event_type):
	"""The timing fields that govern `event_type`, those the doctype has."""
	meta = frappe.get_meta("Livestock Settings")
	return [f for f in EVENT_TIMINGS.get(event_type, ()) if meta.has_field(f)]


def rule_rows():
	types = frappe.get_all(
		EVENT_TYPE,
		fields=["name", "is_active", "posts_stock_entry", "default_store", "must_name_item"],
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
			"enabled": bool(t.is_active),
			"posts_stock_entry": bool(t.posts_stock_entry),
			"item_groups": groups.get(t.name, []),
			"default_store": t.default_store or None,
			"must_name_item": bool(t.must_name_item),
			"timings": _timings(t.name),
		}
		for t in types
	]


@frappe.whitelist()
def stock_rules():
	"""Every event type's switch, stock rule and timings, and the choices the controls offer."""

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
