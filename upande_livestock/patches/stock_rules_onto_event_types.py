# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Each event type carries its own stock rule; the scattered settings go.

What an event takes out of a store was spread over Livestock Settings — a table
of one row per (event, item group), a Drug and a Semen item group, a Drug and a
Semen store, a list of stores searched — plus a "Consumes Drugs" box on each
Livestock Event Type, and they disagreed. Each event type now says it in one
place: Posts Stock Entry, its Item Groups, a Default Store, Must Name an Item
(edited on the Event Type, or all together on the Settings screen's Stock tab).

The rules are written from what the site says today, and never over a type the
farm has already configured:

- a site with the Settings table (kaitet.local) takes its rows as they are;
- a site without one takes the types its "Consumes Drugs" box ticked — or,
  with no such box either (the live site), every type whose form collects
  drugs — drawing on its drug item group, and Service drawing on its semen
  group: the groups and store its pickers already used;
- the Drug store becomes the default store of the drug types, the Semen store
  (else the Drug store) that of Service.

Must Name an Item starts off everywhere: the farm turns it on per type.
"""

import frappe

from upande_livestock.patches._fold import column_exists, drop_column

SETTINGS = "Livestock Settings"
EVENT_TYPE = "Livestock Event Type"
#: What the older sites call these groups when the setting was never filled in
#: (the defaults the drug and semen pickers fell back to).
DEFAULT_GROUPS = {"drug": "DRUGS", "semen": "DAIRY"}
#: Without a mapping or a "Consumes Drugs" column to read (the live site meets
#: Livestock Event Type for the first time), the types whose forms collect
#: drugs — the same set kaitet.local had mapped.
OLD_DRUG_TYPES = ("Vaccination", "Deworming", "Drying Off", "Check Up", "Treatment")
RETIRED_SETTINGS = (
	"custom_event_item_groups", "custom_drug_item_group", "custom_semen_item_group",
	"custom_drug_warehouses", "drug_warehouse", "semen_warehouse",
)


def _single(field):
	rows = frappe.db.sql(
		"SELECT `value` FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, field)
	)
	return rows[0][0] if rows and rows[0][0] else None


def _usable(doctype, name):
	return bool(name) and frappe.db.exists(doctype, name)


def planned_rules():
	"""{event type: [item groups]} from the site's current configuration."""
	if frappe.db.table_exists("Livestock Event Item Group"):
		rows = frappe.db.sql(
			"""SELECT event_type, item_group FROM `tabLivestock Event Item Group`
			   WHERE parenttype = %s AND parentfield = 'custom_event_item_groups'
			   ORDER BY idx""",
			(SETTINGS,),
		)
		if rows:
			plan = {}
			for event_type, group in rows:
				plan.setdefault(event_type, [])
				if group not in plan[event_type]:
					plan[event_type].append(group)
			return plan

	drug_group = _single("custom_drug_item_group") or DEFAULT_GROUPS["drug"]
	semen_group = _single("custom_semen_item_group") or DEFAULT_GROUPS["semen"]
	if column_exists(EVENT_TYPE, "consumes_drugs"):
		drug_types = frappe.db.sql_list(f"SELECT name FROM `tab{EVENT_TYPE}` WHERE consumes_drugs = 1")
	else:
		drug_types = list(OLD_DRUG_TYPES)
	plan = {t: [drug_group] for t in drug_types if t != "Service"}
	plan["Service"] = [semen_group]
	return plan


def execute():
	if not frappe.get_meta(EVENT_TYPE).has_field("posts_stock_entry"):
		return
	# The event types are normally created after_migrate, i.e. after this runs;
	# on a site meeting the doctype for the first time (the live site) there
	# would be nothing to write the rules onto.
	from upande_livestock.install import ensure_livestock_event_types

	ensure_livestock_event_types()
	drug_store = _single("drug_warehouse")
	semen_store = _single("semen_warehouse") or drug_store

	for event_type, groups in planned_rules().items():
		if not frappe.db.exists(EVENT_TYPE, event_type):
			continue
		doc = frappe.get_doc(EVENT_TYPE, event_type)
		if doc.posts_stock_entry or doc.get("stock_item_groups"):
			continue  # the farm has configured this one; leave it
		groups = [g for g in groups if _usable("Item Group", g)]
		if not groups:
			continue
		doc.posts_stock_entry = 1
		for group in groups:
			doc.append("stock_item_groups", {"item_group": group})
		store = semen_store if event_type == "Service" else drug_store
		if _usable("Warehouse", store) and not doc.default_store:
			doc.default_store = store
		doc.flags.ignore_permissions = True
		doc.save()

	frappe.db.delete("Singles", {"doctype": SETTINGS, "field": ("in", RETIRED_SETTINGS)})
	for child in ("Livestock Event Item Group", "Livestock Drug Warehouse"):
		if frappe.db.table_exists(child):
			frappe.db.delete(child, {"parenttype": SETTINGS})
	frappe.db.delete("Custom Field", {"dt": EVENT_TYPE, "fieldname": "consumes_drugs"})
	drop_column(EVENT_TYPE, "consumes_drugs")
	frappe.clear_cache(doctype=SETTINGS)
	frappe.clear_cache(doctype=EVENT_TYPE)
