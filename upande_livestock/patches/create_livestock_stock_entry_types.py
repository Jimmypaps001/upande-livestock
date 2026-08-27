# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Name the livestock stock movements for what they are.

Everything livestock posted was a plain "Material Issue". That is true and
useless: a storekeeper reading the ledger sees stock leaving with no idea
whether it was a deworming round, a vaccination, a vet treating one cow or the
day's feed, and no report can group by it without parsing the remarks.

Each type below has purpose "Material Issue" — the same transaction, labelled.
SCP set this precedent with Chemical Spray and Chemical Loaning.
"""

import frappe

TYPES = [
	("Vaccination", "Material Issue"),
	("Deworming", "Material Issue"),
	("Animal Treatment", "Material Issue"),
	("Animal Health Check", "Material Issue"),
	("Semen Issue", "Material Issue"),
	("Animal Feeding", "Material Issue"),
]


def execute():
	for name, purpose in TYPES:
		if frappe.db.exists("Stock Entry Type", name):
			continue
		doc = frappe.new_doc("Stock Entry Type")
		doc.name = name
		doc.stock_entry_type_name = name if doc.meta.has_field("stock_entry_type_name") else None
		doc.purpose = purpose
		doc.is_standard = 0
		doc.insert(ignore_permissions=True)
