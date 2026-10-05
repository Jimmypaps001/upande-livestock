# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Unhook Animal's `weight_history` table before Weight Record becomes a document.

On the live site "Animal Weight Record" was a child table of Animal, reached
through a Custom Field `weight_history`. rename_livestock_doctypes renames it
onto Livestock Weight Record, which is a submittable document of its own, so
the model sync that follows would leave Animal with a table field pointing at
a doctype that is no longer a table. The field goes here, before that sync;
migrate_legacy_custom_fields turns its rows into weight records afterwards.
"""

import frappe


def execute():
	frappe.db.delete("Custom Field", {"dt": "Animal", "fieldname": "weight_history"})
	frappe.db.delete("Property Setter", {"doc_type": "Animal", "field_name": "weight_history"})
	frappe.clear_cache(doctype="Animal")
