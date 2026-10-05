# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Keep a dropped column's values by writing them into the record's notes.

The cleanup patches drop columns nothing reads any more. On kaitet.local they
were empty; the live site, which ran older code, still has values in some of
them — a lab result, a vet visit date, the accounts an old disposal posted to.
Before a column goes, each value is written into a notes field on the same
record as "[migrated] <Label>: <value>", so the record keeps what it said.

Idempotent: a line already in the notes is not written twice, so a patch that
runs again (or a site that already folded) adds nothing.
"""

import frappe
from frappe.utils import cstr, flt

MARKER = "[migrated]"


def _shown(value):
	"""The value as a note would say it, or None when it says nothing."""
	if value in (None, ""):
		return None
	if isinstance(value, (int, float)) and not isinstance(value, bool):
		return None if flt(value) == 0 else cstr(value)
	return cstr(value).strip() or None


def note_lines(row, labels):
	"""The "[migrated] Label: value" lines for the non-empty columns of `row`."""
	lines = []
	for column, label in labels.items():
		shown = _shown(row.get(column))
		if shown is not None:
			lines.append(f"{MARKER} {label}: {shown}")
	return lines


def append_lines(doctype, name, notes_field, current, lines):
	"""Add `lines` that are not already in `current` to the notes field."""
	new = [line for line in lines if line not in (current or "")]
	if not new:
		return
	text = "\n".join(([current] if current else []) + new)
	frappe.db.set_value(doctype, name, notes_field, text, update_modified=False)


def fold_into_notes(doctype, labels, notes_field, where=None):
	"""Write each record's values in `labels` (column -> label) into `notes_field`.

	`where` narrows the records (raw SQL): a default stamped on every row is
	only worth keeping on the rows where it meant something.
	"""
	present = {c: l for c, l in labels.items() if column_exists(doctype, c)}
	if not present or not column_exists(doctype, notes_field):
		return
	columns = ", ".join(f"`{c}`" for c in present)
	for row in frappe.db.sql(
		f"SELECT name, `{notes_field}` AS notes, {columns} FROM `tab{doctype}`"
		+ (f" WHERE {where}" if where else ""),
		as_dict=True,
	):
		append_lines(doctype, row.name, notes_field, row.notes, note_lines(row, present))


def column_exists(doctype, column):
	"""`has_column`, asked of the database rather than of the cached column list.

	Frappe caches each table's columns; a patch that adds or drops columns, or
	runs right after the model sync made some, would read a stale answer.
	"""
	frappe.client_cache.delete_value(f"table_columns::tab{doctype}")
	return frappe.db.has_column(doctype, column)


def drop_column(doctype, column):
	if column_exists(doctype, column):
		frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{column}`")
		frappe.client_cache.delete_value(f"table_columns::tab{doctype}")
