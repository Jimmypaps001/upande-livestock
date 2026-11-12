# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Switch every existing event type on.

Each Livestock Event Type now has an Enabled switch (its `is_active` box,
relabelled; see common/event_types). Off, the event disappears from the menus
and alerts and a new one is refused. Before this the box changed nearly
nothing, so a type left unticked on some site was never a decision to stop
recording it — and turning it into one silently, at migrate, would hide forms
a farm uses every day. Every type starts on; a farm switches off what it does
not do in Settings → Events.
"""

import frappe


def execute():
	frappe.reload_doc("upande_livestock", "doctype", "livestock_event_type")
	frappe.db.sql(
		"UPDATE `tabLivestock Event Type` SET is_active = 1 WHERE IFNULL(is_active, 0) = 0"
	)
