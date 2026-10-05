# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Save the Settings screen's Stock tab back onto the event types (see stock_rules)."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.settings.stock_rules import EVENT_TYPE, rule_rows


@frappe.whitelist()
def save_stock_rules(payload=None):
	"""Write the rules back onto their event types; only rows that changed are saved.

	Each event type is saved as a document, so its own validation runs and the
	change shows in that event type's history — the record of who changed what
	an event posts, and when.
	"""

	def go():
		guard(EVENT_TYPE)
		if not frappe.has_permission(EVENT_TYPE, "write"):
			frappe.throw(_("You are not permitted to change event types."), frappe.PermissionError)
		sent = as_dict(payload).get("rules")
		if not isinstance(sent, list):
			frappe.throw(_("Send the rules to save."))

		changed = []
		for rule in sent:
			name = (rule or {}).get("event_type")
			if not name or not frappe.db.exists(EVENT_TYPE, name):
				frappe.throw(_("{0} is not an event type.").format(name))
			posts = bool(rule.get("posts_stock_entry"))
			groups = list(dict.fromkeys(g for g in rule.get("item_groups") or [] if g))
			store = rule.get("default_store") or None
			must = bool(rule.get("must_name_item")) and posts
			for g in groups:
				if not frappe.db.exists("Item Group", g):
					frappe.throw(_("{0} is not an item group.").format(g))
			if store and not frappe.db.exists("Warehouse", store):
				frappe.throw(_("{0} is not a warehouse.").format(store))
			if posts and not groups:
				frappe.throw(_("{0} posts stock but names no item group to draw on.").format(name))

			doc = frappe.get_doc(EVENT_TYPE, name)
			before = (bool(doc.posts_stock_entry), [r.item_group for r in doc.stock_item_groups],
			          doc.default_store or None, bool(doc.must_name_item))
			if before == (posts, groups if posts else [], store if posts else None, must):
				continue
			doc.posts_stock_entry = int(posts)
			doc.set("stock_item_groups", [{"item_group": g} for g in groups] if posts else [])
			doc.default_store = store if posts else None
			doc.must_name_item = int(must)
			doc.save()
			changed.append(name)

		return {"ok": True, "changed": changed, "rules": rule_rows()}

	return run(go, "livestock save_stock_rules failed")
