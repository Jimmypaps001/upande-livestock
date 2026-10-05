# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One outcome per service, and no service or calving facts on a Movement.

A Service's result is `pregnancy_confirmation_status` — every breeding list,
alert and forecast reads it. It had two shadows written beside it:
`service_status` (read only by the dashboard's events table) and
`custom_status_after_test` (read by nothing, and written as "Successful", a
value its own Select did not offer). Both columns go.

Four Selects had no blank first option, and a Select without one defaults to
its first option on every new document. So every Movement, Vaccination and
Feeding carried "A.I." as its service type, "Pending" as its pregnancy check,
"Live Birth" and "Male" as its calving — and `semen_qty`'s default of 1 put a
straw on each of them. The Selects now start blank; this clears what they
stamped on the event types they do not describe. No query was misled — each
one filters to the event type first — but every form and export was.
"""

import frappe

DROPPED = ("service_status", "custom_status_after_test")

#: field -> the event types it describes. Anything else holding it was stamped.
BELONGS_TO = {
	"service_type": ("Service",),
	"pregnancy_confirmation_status": ("Service",),
	"semen_qty": ("Service",),
	# A Birth keeps its own calf_sex and is_stillborn; these were stamped on
	# it too — "Male" on four heifer calves, "Live Birth" on 67 stillborns.
	"custom_calving_outcome": ("Calving",),
	"custom_calf_sex": ("Calving",),
}


def execute():
	frappe.db.delete("Custom Field", {"dt": "Livestock Event", "fieldname": ("in", DROPPED)})
	frappe.db.delete("Property Setter", {"doc_type": "Livestock Event", "field_name": ("in", DROPPED)})

	for field, types in BELONGS_TO.items():
		if frappe.db.has_column("Livestock Event", field):
			frappe.db.sql(
				f"""UPDATE `tabLivestock Event` SET `{field}` = %(blank)s
				    WHERE event_type NOT IN %(types)s""",
				# A Float column is NOT NULL; its blank is 0.
				{"types": types, "blank": 0 if field == "semen_qty" else None},
			)

	frappe.clear_cache(doctype="Livestock Event")
	for column in DROPPED:
		if frappe.db.has_column("Livestock Event", column):
			frappe.db.sql_ddl(f"ALTER TABLE `tabLivestock Event` DROP COLUMN `{column}`")
