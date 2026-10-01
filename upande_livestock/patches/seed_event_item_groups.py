# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Carry today's configuration into the per-event item group mapping.

Nothing is invented. The event types flagged with `consumes_drugs = 1` already
draw on `custom_drug_item_group`, and treatments already issue drugs from it
through a health case — so rows for those flagged types plus Treatment record
what the site already does. An event type with no mapped group consumes nothing
and shows no items list, which is exactly what `consumes_drugs = 0` meant.

A site that configured no drug item group gets no rows and behaves as it did.
A site that flagged a drug-consuming type without a deploy gets a row for it,
and a site that un-flagged one gets no row invented.

SERVICE IS DELIBERATELY NOT MAPPED. It would have to use
`custom_semen_item_group`, which on live is `Dairy Others` — 410 items, 63 of
them straws — so mapping it would replace a working straw picker with a worse
one. Service is mapped by hand once a site has a group holding straws alone.
"""

import frappe

SETTINGS = "Livestock Settings"
TABLE = "custom_event_item_groups"


def execute():
	ensure_treatment_event_type()
	seed_rows_from_the_drug_group()


def ensure_treatment_event_type():
	"""`Treatment` exists to be the mapping's key.

	It is not separately recordable — the screens are hardcoded pages, not
	generated from this DocType — so the row offers nobody a new form. It is
	here because the farm calls the thing that consumes the drug a treatment,
	and a settings line reading `Treatment -> Dairy Drugs` is the one a person
	can check.
	"""
	if not frappe.db.table_exists("Livestock Event Type"):
		return
	if frappe.db.exists("Livestock Event Type", "Treatment"):
		return
	doc = frappe.new_doc("Livestock Event Type")
	doc.name = "Treatment"  # autoname is Prompt
	doc.is_active = 1
	doc.creates_animal = 0
	doc.description = "Drugs given to a sick animal, recorded under her health case."
	doc.insert(ignore_permissions=True)


def seed_rows_from_the_drug_group():
	"""One row per drug-consuming type, pointing at the configured group.

	Drug-consuming types are those flagged with consumes_drugs = 1, plus
	Treatment (which this patch creates). Nothing is invented: a site that
	flags a type gets a row for it, and one that un-flags gets no row.
	"""
	settings = frappe.get_single(SETTINGS)
	if not settings.meta.has_field(TABLE):
		return

	group = settings.get("custom_drug_item_group")
	if not group:
		return

	# Read the flagged drug-consuming types from the database
	flagged = frappe.get_all(
		"Livestock Event Type",
		filters={"consumes_drugs": 1},
		pluck="name",
	)
	# Add Treatment unconditionally: the patch creates it, and it has no flag
	drug_consuming = set(flagged) | {"Treatment"}

	have = {(r.event_type, r.item_group) for r in settings.get(TABLE) or []}
	added = 0
	for event_type in drug_consuming:
		if (event_type, group) in have:
			continue
		if not frappe.db.exists("Livestock Event Type", event_type):
			continue
		settings.append(TABLE, {"event_type": event_type, "item_group": group})
		added += 1

	if added:
		settings.flags.ignore_permissions = True
		settings.save()
