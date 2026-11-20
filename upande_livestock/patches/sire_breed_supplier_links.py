# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Livestock Sire: Breed matched to the Breed doctype, Supplier fetched from the straw Item.

Breed was typed text; a Link holds only a Breed's name, so each value is matched by
name, case-insensitively, and left blank when no Breed matches (listed in the log).
Supplier was typed text and is now read-only, fetched from the straw Item
(sire_items.fetch_supplier); a live bull has none.
"""

import frappe

from upande_livestock.serverscripts.common.sire_items import fetch_supplier


def execute():
	breeds = {b.lower(): b for b in frappe.get_all("Breed", pluck="name")}
	unmatched = []
	for s in frappe.get_all("Livestock Sire", fields=["name", "breed", "semen_item", "sire_type", "supplier"]):
		breed = (s.breed or "").strip()
		fixed = breeds.get(breed.lower()) if breed else None
		if breed and not fixed:
			unmatched.append((s.name, breed))
		supplier = fetch_supplier(s.semen_item) if s.sire_type == "Semen" and s.semen_item else None
		if (fixed or None) != (s.breed or None):
			frappe.db.set_value("Livestock Sire", s.name, "breed", fixed, update_modified=False)
		if supplier != (s.supplier or None):
			frappe.db.set_value("Livestock Sire", s.name, "supplier", supplier, update_modified=False)
	if unmatched:
		print("Livestock Sire breeds with no Breed, left blank:", unmatched)
