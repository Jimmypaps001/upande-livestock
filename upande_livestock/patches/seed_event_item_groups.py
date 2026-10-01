# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Carry today's configuration into the per-event item group mapping.

Nothing is invented. The four types carrying `consumes_drugs = 1` already draw
on `custom_drug_item_group`, and treatments already issue drugs from it through
a health case — so those five rows record what the site already does. An event
type with no mapped group consumes nothing and shows no items list, which is
exactly what `consumes_drugs = 0` meant.

A site that configured no drug item group gets no rows and behaves as it did.

SERVICE IS DELIBERATELY NOT MAPPED. It would have to use
`custom_semen_item_group`, which on live is `Dairy Others` — 410 items, 63 of
them straws — so mapping it would replace a working straw picker with a worse
one. Service is mapped by hand once a site has a group holding straws alone.
"""

import frappe

SETTINGS = "Livestock Settings"
TABLE = "custom_event_item_groups"

#: Exactly the types carrying `consumes_drugs = 1`, plus Treatment, which
#: consumes through a health case rather than an event.
DRUG_CONSUMING = ("Vaccination", "Deworming", "Check Up", "Drying Off", "Treatment")


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
	"""One row per drug-consuming type, pointing at the configured group."""
	try:
		settings = frappe.get_single(SETTINGS)
	except Exception:
		return
	if not settings.meta.has_field(TABLE):
		return

	group = settings.get("custom_drug_item_group")
	if not group:
		return

	have = {(r.event_type, r.item_group) for r in settings.get(TABLE) or []}
	added = 0
	for event_type in DRUG_CONSUMING:
		if (event_type, group) in have:
			continue
		if not frappe.db.exists("Livestock Event Type", event_type):
			continue
		settings.append(TABLE, {"event_type": event_type, "item_group": group})
		added += 1

	if added:
		settings.flags.ignore_permissions = True
		settings.save()
