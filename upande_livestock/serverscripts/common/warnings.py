# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Things the answer must say aloud, that never stop the action.

The sibling of `stock.note_warning`: a rule that Warns (an inbreeding risk)
records its sentence here, `envelope.run` puts the sentences in the response as
`warnings: [str]`, and the phone shows them on the success screen. The desk gets
the same sentence as an orange `msgprint`.
"""

import frappe


def note(message):
	warnings = frappe.flags.get("livestock_warnings") or []
	if message not in warnings:
		warnings.append(message)
	frappe.flags.livestock_warnings = warnings


def made():
	"""The sentences noted so far, cleared as they are read."""
	warnings = frappe.flags.get("livestock_warnings") or []
	frappe.flags.livestock_warnings = []
	return warnings
