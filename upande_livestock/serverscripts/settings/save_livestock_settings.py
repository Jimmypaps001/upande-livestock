# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Apply a patch of changed Livestock Settings scalars.

Guarded on Livestock Settings itself, not on a role: these fields decide how
the whole farm behaves — how long a gestation is, which warehouse the milk is
posted into, which account the journal entry credits — and being able to open
the app is not the same thing as being allowed to change that.

Two decisions worth knowing about before editing this file.

**It writes fields, not the document.** `frappe.get_single(...).save()` would be
the obvious implementation and it is the wrong one here: saving this Single
coerces every *unset* Int through `cint(None)` and persists an explicit 0 (see
`install.ensure_livestock_timing_defaults`), which silently disables every age
and interval guard in `serverscripts.common.guards`. That has already happened
on this site once — `patches.repair_zeroed_age_interval_settings` is the
clean-up. Writing only the fields the caller actually changed cannot do it.

The cost of not saving the document is that `LivestockSettings.validate` does
not run, so the one rule it holds is called directly instead:
`reject_invalid_zeros`, in the same words, from the same place. Anything else
added to `validate` later has to be added to this call site too, which is why
the rule lives in a function of its own rather than inline in `validate`.

**It accepts only fieldnames the doctype has.** The payload is checked against
`editable_fieldnames()`, read off the meta, before anything is written. A dict
passed straight to `frappe.db.set_single_value` lets the caller pick the column
— including `owner`, `modified_by`, or a field on a doctype that does not exist
yet — and `tabSingles` will happily hold all of it.
"""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.settings._shared import (
	DOCTYPE,
	coerce_for_write,
	docfield,
	editable_fieldnames,
	values,
)
from upande_livestock.upande_livestock.doctype.livestock_settings.livestock_settings import (
	reject_invalid_zeros,
)


@frappe.whitelist()
def save_livestock_settings(payload=None):
	"""Write the changed scalars. See the module docstring."""

	def go():
		guard(DOCTYPE)
		# `guard` asks whether this user may create the doctype, which for a
		# Single is the same grant as editing it — every role that can write
		# Livestock Settings has it. The write permission is asserted in its
		# own right here so a farm that later splits the two cannot end up with
		# an endpoint that edits settings on a create-only grant.
		if not frappe.has_permission(DOCTYPE, "write"):
			frappe.throw(_("You are not permitted to change {0}.").format(DOCTYPE), frappe.PermissionError)

		changes = as_dict(payload)
		if not isinstance(changes, dict):
			frappe.throw(_("Send the settings to change as a set of field/value pairs."))
		if not changes:
			frappe.throw(_("Nothing to save."))

		unknown = sorted(set(changes) - editable_fieldnames())
		if unknown:
			frappe.throw(_("Livestock Settings has no field called {0}.").format(", ".join(unknown)))

		# Coerce and check everything before writing anything: a patch that is
		# refused halfway leaves the farm running on half a change, and which
		# half depends on dict ordering.
		before = values()
		wanted = {}
		for fieldname, raw in changes.items():
			wanted[fieldname] = coerce_for_write(docfield(fieldname), raw)
		reject_invalid_zeros(wanted)

		changed = {}
		for fieldname, value in wanted.items():
			if before.get(fieldname) == value:
				continue
			frappe.db.set_single_value(DOCTYPE, fieldname, value)
			changed[fieldname] = {"from": before.get(fieldname), "to": value}

		return {
			"ok": True,
			"changed": changed,
			"unchanged": sorted(set(wanted) - set(changed)),
			# The page redraws from this rather than from its own optimistic
			# copy, so what it shows after a save is what is stored.
			"values": values(),
		}

	return run(go, "livestock save_livestock_settings failed")
