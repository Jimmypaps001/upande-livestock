# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Replace the rows of one Livestock Settings child table."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.settings._shared import (
	DOCTYPE,
	coerce_for_write,
	table_columns,
	table_docfield,
	table_rows,
)


@frappe.whitelist()
def save_livestock_settings_table(payload=None):
	"""Save a whole list — feed stores, bought-in concentrates, the ladder.

	THE LISTS WERE READ-ONLY AND THE PAGE SENT YOU TO THE DESK. Which stores
	hold feed is a farm decision, made by the person running the farm, and
	"open ERPNext, find Livestock Settings, add a row to a grid" is not a thing
	that person does — so in practice the list was whatever it was on the day it
	was set up.

	A LIST IS SAVED WHOLE, not row by row. Adding, removing and reordering are
	one edit to the operator, and three endpoints racing each other on the same
	table is how a farm ends up with a store listed twice and its feed counted
	twice with it.

	IT DOES NOT SAVE THE PARENT. `frappe.get_single(...).save()` is the obvious
	implementation and it is the one that cannot be used here: saving this
	Single coerces every unset Int through cint(None) and persists an explicit
	0, which switches off every age and interval guard on the farm. That has
	happened on this site once already — `patches.repair_zeroed_age_interval_
	settings` is the clean-up. Child rows are written in their own right
	instead, so nothing the caller did not name can change.

	Rows that survive an edit keep their names, so a row is edited rather than
	deleted and recreated. The difference shows in the modification log, which
	is the only record of who changed the feed stores and when.
	"""

	def go():
		guard(DOCTYPE)
		if not frappe.has_permission(DOCTYPE, "write"):
			frappe.throw(
				_("You are not permitted to change {0}.").format(DOCTYPE), frappe.PermissionError
			)

		d = as_dict(payload)
		df = table_docfield(d.get("fieldname"))
		columns = table_columns(df)
		sent = d.get("rows")
		if sent is None:
			frappe.throw(_("Send the rows to save, even if the list is being emptied."))
		if not isinstance(sent, list):
			frappe.throw(_("The rows have to be a list."))

		# Coerce and check the whole list before writing any of it: a list saved
		# halfway is a farm running on half a change, and which half depends on
		# the order the rows happened to arrive in.
		wanted = []
		seen = set()
		for position, row in enumerate(sent, start=1):
			if not isinstance(row, dict):
				frappe.throw(_("Row {0} is not a set of values.").format(position))
			fields = {}
			for cdf in columns:
				value = coerce_for_write(cdf, row.get(cdf.fieldname))
				if cdf.reqd and value in (None, ""):
					frappe.throw(
						_("Row {0} has no {1}.").format(
							position, cdf.label or frappe.unscrub(cdf.fieldname)
						)
					)
				fields[cdf.fieldname] = value
			key = _key(columns, fields)
			if key is not None:
				# The same store listed twice counts its feed twice. Nothing
				# downstream would notice, which is why it is refused here.
				if key in seen:
					frappe.throw(_("Row {0} is already on the list.").format(position))
				seen.add(key)
			wanted.append({"name": (row.get("name") or "").strip() or None, "idx": position,
			               "fields": fields})

		had = {r["name"]: r for r in table_rows(df)}
		keeping = {w["name"] for w in wanted if w["name"]}
		unknown = sorted(keeping - set(had))
		if unknown:
			frappe.throw(_("Row {0} is not on this list any more — reload the page.").format(unknown[0]))

		removed = [name for name in had if name not in keeping]
		for name in removed:
			frappe.delete_doc(df.options, name, force=True, ignore_permissions=True)

		added = 0
		for want in wanted:
			if want["name"]:
				frappe.db.set_value(
					df.options, want["name"], {**want["fields"], "idx": want["idx"]}
				)
				continue
			child = frappe.new_doc(df.options)
			child.update(want["fields"])
			child.parent = DOCTYPE
			child.parenttype = DOCTYPE
			child.parentfield = df.fieldname
			child.idx = want["idx"]
			child.insert(ignore_permissions=True)
			added += 1

		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		return {
			"ok": True,
			"fieldname": df.fieldname,
			"added": added,
			"removed": len(removed),
			# The page redraws from this rather than from its own optimistic
			# copy, so what it shows after a save is what is stored.
			"rows": table_rows(df),
		}

	return run(go, "livestock save_livestock_settings_table failed")


def _key(columns, fields):
	"""What makes a row the same row as another, or None if nothing does.

	The first Link column: a feed store, a concentrate item, a herd on the
	ladder. Free text beside it is a note about the row, not the row.
	"""
	for cdf in columns:
		if cdf.fieldtype == "Link":
			return fields.get(cdf.fieldname)
	return None
