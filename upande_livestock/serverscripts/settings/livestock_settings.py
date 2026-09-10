# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The whole Livestock Settings document, in one call.

Nothing read this Single whole before. The handset asks for one field at a time
through `frappe.client.get_single_value`, which is right for the two or three
values a screen needs and absurd for a settings page: fifty scalars is fifty
round trips before the first control can be drawn.

It returns the doctype's own tabs and sections along with the values, so the
page is a mirror of Livestock Settings rather than a second copy of it. A field
added on the desk appears on the page with nothing to change here — and, more
to the point, a field added on the desk cannot go missing from the page without
anyone noticing.

Three things travel with each field because the page cannot work them out and
must not guess:

* `zero` — whether a 0 in that box switches the rule off (two fields) or is the
  historical bug the DocType now refuses (the rest). See `_shared.zero_rule`.
* `posts` — whether a wrong value there posts stock or money somewhere else
  instead of raising.
* `null` values — a field with no row at all reads back as `None`, not 0, so
  "not set, the default applies" and "deliberately 0" stay different answers.

Read-guarded on Livestock Settings, which is also what decides whether the page
is offered at all: `can_write` says whether saving is even worth showing.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.settings._shared import DOCTYPE, layout, tables, values


@frappe.whitelist()
def livestock_settings():
	"""Every scalar, every child-table row, and the layout they sit in."""

	def go():
		guard_read(DOCTYPE)
		return {
			"ok": True,
			"doctype": DOCTYPE,
			"tabs": layout(),
			"values": values(),
			"tables": tables(),
			# Read permission is enough to open this page; write is not implied
			# by it. The page shows the settings either way and only offers Save
			# when this is true — the endpoint refuses regardless.
			"can_write": bool(frappe.has_permission(DOCTYPE, "write")),
		}

	return run(go, "livestock livestock_settings failed")
