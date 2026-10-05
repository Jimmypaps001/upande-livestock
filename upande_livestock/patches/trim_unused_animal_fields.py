# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Drop the Animal columns nothing keeps.

Read by nothing at all: `coat_colour`, `in_treatment`, `last_vaccination_date`,
`last_deworming_date`, `next_due_event`, `last_service_sire`, and
`milk_safe_date` — the withdrawal date lives on the Health Case.

Read, but never written, so every reader saw 0:

- `days_in_milk` — the dashboard's milking count. Being in milk is now
  standing in a lactation group, per Herd Movement settings.
- `total_services`, `conception_rate` — counted off the Service events by
  common.animal.service_record.
- `current_book_value` — written once at purchase and never depreciated, and
  0 on every migrated animal. The cull case reads the Asset's value instead.

Frappe never drops a column on its own, so a removed field's old values would
sit in the table indefinitely, looking like data.
"""

import frappe

from upande_livestock.patches._fold import fold_into_notes

DROPPED = (
	"coat_colour",
	"in_treatment",
	"milk_safe_date",
	"last_vaccination_date",
	"last_deworming_date",
	"next_due_event",
	"last_service_sire",
	"days_in_milk",
	"conception_rate",
	"total_services",
	"current_book_value",
)


#: Facts with no other home, kept in the animal's remarks before their column
#: goes. The live site holds vaccination and deworming dates on most animals.
#: The derived figures (days in milk, services, conception rate, book value)
#: are recomputed from the record, so they are not kept.
FOLDED = {
	"coat_colour": "Coat colour",
	"last_vaccination_date": "Last vaccination",
	"last_deworming_date": "Last deworming",
	"next_due_event": "Next due",
	"last_service_sire": "Last service sire",
	"milk_safe_date": "Milk safe from",
}


def execute():
	fold_into_notes("Animal", FOLDED, "remarks")
	frappe.db.delete("Property Setter", {"doc_type": "Animal", "field_name": ("in", DROPPED)})
	frappe.clear_cache(doctype="Animal")
	for column in DROPPED:
		if frappe.db.has_column("Animal", column):
			frappe.db.sql_ddl(f"ALTER TABLE `tabAnimal` DROP COLUMN `{column}`")
