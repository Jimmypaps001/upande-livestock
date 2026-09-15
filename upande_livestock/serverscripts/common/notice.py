# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Headings for the notices the farm reads, with a real icon rather than a glyph.

NO EMOJI. An emoji is a font glyph: it renders as somebody else's drawing at
somebody else's weight, differs on every platform, reads as a cartoon on a
document people sign things from, and cannot take the colour of the thing it is
marking. The desk notices in this package were built out of them — a cow's face
on a pregnancy refusal, a siren on an overdue check — and they were doing real
work, so they are replaced rather than simply deleted.

`public/icons/` holds the drawings, in the same line language as the app's own,
and `currentColor` means one asset serves a red warning and a grey note alike.

WHERE AN ICON BELONGS AND WHERE IT DOES NOT. A ToDo in a list of forty is
scanned, and a severity mark earns its place. A validation dialog that stops
somebody mid-record is READ, and an image there is one more thing that can fail
to load in front of a person who is already blocked — so `heading()` is for
notices and refusals get plain words.
"""

import frappe

#: Where the drawings live. One place, so a renamed asset breaks in one file.
ICON_BASE = "/assets/upande_livestock/icons"

#: The set that exists. Asking for anything else is a typo, and a typo that
#: silently rendered a broken image would be worse than the emoji.
ICONS = ("warning", "clock", "calendar", "check", "heat", "search", "repeat", "blocked")


def icon(name, size=15):
	"""One icon as an `<img>`, sized to sit on a line of text.

	Vertical alignment is set here rather than left to the surface: a ToDo
	description is rendered inside somebody else's stylesheet, and an icon
	sitting on the baseline instead of beside the text is what makes an
	otherwise fine notice look broken.
	"""
	if name not in ICONS:
		frappe.throw(frappe._("There is no {0} icon.").format(name))
	return (
		f'<img src="{ICON_BASE}/{name}.svg" alt="" width="{size}" height="{size}" '
		f'style="vertical-align:-2px;margin-right:6px" />'
	)


def heading(name, text):
	"""A notice's first line: an icon, then the thing it is about, in bold."""
	return f"<b>{icon(name)}{frappe.utils.escape_html(text)}</b>"
