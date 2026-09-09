"""Reload the doctypes that gained backdating fields.

No data migration. Every existing record keeps custom_is_backdated = 0, which
is the truth about them: they were entered live, on the day they happened.
"""

import frappe

DOCTYPES = [
	"livestock_settings",
	"livestock_event",
	"livestock_disposal",
	"livestock_health_case",
	"livestock_diagnosis",
	"livestock_weight_record",
	"milk_recording",
]


def execute():
	for name in DOCTYPES:
		frappe.reload_doc("upande_livestock", "doctype", name)
