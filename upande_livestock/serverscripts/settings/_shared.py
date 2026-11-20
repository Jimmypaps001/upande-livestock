# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the Settings page may see, and what it may change.

One module rather than a copy in each endpoint: the reader and the writer have
to agree on exactly which fields exist, or the page offers a control whose
value the server then refuses.

The field list is read off the DocType meta on every call and is never written
down here. An endpoint that keeps its own list of fieldnames goes stale the
first time somebody adds a field to Livestock Settings, and it fails silently —
the page simply never shows the new setting, and nobody finds out.

Three things this module exists to get right:

* **Only real fields.** `editable_fieldnames()` is the whitelist the writer
  checks a payload against. Handing a caller's dict straight to
  `frappe.db.set_single_value` would let the caller pick the column.
* **A 0 is not a blank.** `frappe.db.get_single_value` casts, so an unset Int
  comes back as 0 — indistinguishable from a farm that deliberately configured
  0, which is how `post_calving_min_service_days` is turned off. `values()`
  reads the raw `tabSingles` rows instead and keeps `None` as `None`, so the
  page can say "not set, the default applies" where that is what is true, and
  warn where a real 0 is switching a guard off.
* **A link that names nothing.** `custom_feed_wip_warehouse` and its five
  neighbours post stock and journal entries. A wrong value there does not
  raise; it posts somewhere else. `set_single_value` does no link validation of
  its own, so `coerce_for_write` does it here.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from upande_livestock.upande_livestock.doctype.livestock_settings.livestock_settings import (
	ZERO_IS_INVALID,
	ZERO_MEANS_DISABLED,
)

DOCTYPE = "Livestock Settings"

# Structure, not data: read for their labels, never offered as a control.
LAYOUT_FIELDTYPES = frozenset({"Tab Break", "Section Break", "Column Break", "Fold"})
# Decoration with no stored value.
DISPLAY_FIELDTYPES = frozenset({"HTML", "Heading", "Button", "Image"})
TABLE_FIELDTYPES = frozenset({"Table", "Table MultiSelect"})
NUMERIC_FIELDTYPES = frozenset({"Int", "Float", "Percent", "Currency"})

# The links that do not error when they are wrong — they post somewhere wrong.
# Flagged to the page so an operator can see which choices move stock and money
# before they touch one, rather than after the month-end reconciliation.
POSTING_LINKS = frozenset(
	{
		"custom_feed_wip_warehouse",
		"custom_milk_target_warehouse",
		"custom_milk_discard_warehouse",
		"custom_milk_item",
		"custom_milking_stock_entry_type",
		"semen_item",
		"custom_default_company",
		"custom_default_credit_account",
		# Books a concentrate mix somewhere. Wrong here does not raise either.
		"custom_concentrate_cost_center",
	}
)


def scalar_docfields():
	"""Every field on the doctype that holds one editable value."""
	return [
		df
		for df in frappe.get_meta(DOCTYPE).fields
		if df.fieldtype not in LAYOUT_FIELDTYPES
		and df.fieldtype not in DISPLAY_FIELDTYPES
		and df.fieldtype not in TABLE_FIELDTYPES
	]


def table_docfields():
	return [df for df in frappe.get_meta(DOCTYPE).fields if df.fieldtype in TABLE_FIELDTYPES]


def editable_fieldnames() -> frozenset:
	"""The only fieldnames a write is allowed to name.

	Read-only fields are shown, never written: the page cannot be a way round a
	field the doctype says only the system sets.
	"""
	return frozenset(df.fieldname for df in scalar_docfields() if not df.read_only)


# Who may change what. Livestock Manager and System Manager hold write on the
# doctype and may change everything. An Accounts Manager is not a livestock
# role, but the accounts, cost centres and insurance mapping are theirs to set —
# so they may write the fields on the Accounts tab and nothing else.
ACCOUNTS_ROLE = "Accounts Manager"
ACCOUNTS_TAB = "tab_accounts"


def accounts_fieldnames() -> frozenset:
	"""Every field (scalar or list) on the Accounts & Insurance tab.

	Read off the layout, so a field somebody adds to that tab — the insurance
	flow's, say — becomes the Accounts Manager's with nothing to change here.
	"""
	names = set()
	for tab in layout():
		if tab["fieldname"] != ACCOUNTS_TAB:
			continue
		for section in tab["sections"]:
			names.update(f["fieldname"] for f in section["fields"])
			names.update(section["tables"])
	return frozenset(names)


def writable_fieldnames() -> frozenset:
	"""What this user may write: all of it, the accounts tab, or nothing."""
	if frappe.has_permission(DOCTYPE, "write"):
		return frozenset(df.fieldname for df in frappe.get_meta(DOCTYPE).fields
			if df.fieldtype not in LAYOUT_FIELDTYPES and df.fieldtype not in DISPLAY_FIELDTYPES
			and not df.read_only)
	if ACCOUNTS_ROLE in frappe.get_roles():
		return accounts_fieldnames()
	return frozenset()


def guard_write(names) -> None:
	"""Throw unless the user may write every one of `names`."""
	allowed = writable_fieldnames()
	if not allowed:
		frappe.throw(_("You are not permitted to change {0}.").format(DOCTYPE), frappe.PermissionError)
	refused = sorted(set(names) - allowed)
	if refused:
		frappe.throw(
			_("You are not permitted to change {0}.").format(", ".join(refused)),
			frappe.PermissionError,
		)


def docfield(fieldname):
	return frappe.get_meta(DOCTYPE).get_field(fieldname)


def zero_rule(fieldname):
	"""What a stored 0 means for this field, in the page's words.

	`disables` — 0 is a real configuration and switches the rule off.
	`invalid`  — 0 can only be the historical bug that
	             `repair_zeroed_age_interval_settings` exists to undo, and the
	             DocType refuses it.
	"""
	if fieldname in ZERO_MEANS_DISABLED:
		return "disables"
	if fieldname in ZERO_IS_INVALID:
		return "invalid"
	return None


def cast_stored(df, value):
	"""The stored string as the page should read it — `None` when there is no
	row at all, which is not the same answer as 0."""
	if df.fieldtype == "Check":
		# A checkbox has no third state: no row means off.
		return 1 if cint(value) else 0
	if value in (None, ""):
		return None
	if df.fieldtype == "Int":
		return cint(value)
	if df.fieldtype in NUMERIC_FIELDTYPES:
		return flt(value)
	return str(value)


def values() -> dict:
	"""Every scalar's stored value, keyed by fieldname."""
	stored = frappe.db.get_singles_dict(DOCTYPE)
	return {df.fieldname: cast_stored(df, stored.get(df.fieldname)) for df in scalar_docfields()}


def coerce_for_write(df, value):
	"""The value to store for `df`, or a throw an operator can act on.

	Deliberately strict where `cint`/`flt` are forgiving: `cint("nine")` is 0,
	and 0 on a timing field is "rule off". A typo must be refused, not silently
	turned into the most dangerous value the field has.
	"""
	label = df.label or frappe.unscrub(df.fieldname)

	if df.fieldtype == "Check":
		ticked = cint(value)
		if ticked not in (0, 1):
			frappe.throw(_("{0} is a tick box — it is either on or off.").format(label))
		return ticked

	if df.fieldtype in NUMERIC_FIELDTYPES:
		if value in (None, ""):
			frappe.throw(
				_(
					"{0} needs a number. Leaving the box empty is not a setting — and typing 0 "
					"does not clear the rule, it switches it off."
				).format(label)
			)
		try:
			number = float(str(value).strip())
		except (TypeError, ValueError):
			frappe.throw(_("{0} has to be a number. {1} is not one.").format(label, value))
		if number < 0:
			frappe.throw(_("{0} cannot be negative.").format(label))
		if df.fieldtype == "Int":
			if number != int(number):
				frappe.throw(_("{0} is a whole number of days or months, not {1}.").format(label, value))
			return int(number)
		return flt(number)

	if df.fieldtype == "Link":
		name = str(value).strip() if value is not None else ""
		if not name:
			# Clearing a link is a real choice — an unset Default Calf Herd means
			# "work it out from the herd ages" — so it is allowed, not refused.
			return None
		if not frappe.db.exists(df.options, name):
			frappe.throw(
				_("There is no {0} called {1}. Pick one from the list rather than typing it.").format(
					df.options, name
				)
			)
		return name

	if df.fieldtype in ("Date", "Time", "Datetime"):
		if value in (None, ""):
			return None
		try:
			from frappe.utils import get_datetime, get_time, getdate

			{"Date": getdate, "Time": get_time, "Datetime": get_datetime}[df.fieldtype](value)
		except Exception:
			frappe.throw(_("{0} is not a valid {1} for {2}.").format(value, df.fieldtype.lower(), label))
		return str(value).strip()

	if df.fieldtype == "Select":
		choices = [c for c in (df.options or "").split("\n")]
		name = "" if value is None else str(value)
		if name and name not in choices:
			frappe.throw(_("{0} is not one of the choices for {1}.").format(name, label))
		return name or None

	return None if value in (None, "") else str(value)


def layout() -> list:
	"""The doctype's own tabs and sections, in the doctype's own order.

	The page is a mirror of Livestock Settings; walking the meta is what makes
	that true rather than a claim. A field moved between tabs on the desk moves
	on the page too, with nothing to change here.
	"""
	tabs = []
	tab = None
	section = None

	def open_tab(label, fieldname):
		nonlocal tab, section
		tab = {"fieldname": fieldname, "label": label, "sections": []}
		tabs.append(tab)
		section = None

	def open_section(label, description, fieldname):
		nonlocal section
		if tab is None:
			open_tab(_("General"), "_tab")
		section = {
			"fieldname": fieldname,
			"label": label,
			"description": description,
			"fields": [],
			"tables": [],
		}
		tab["sections"].append(section)

	for df in frappe.get_meta(DOCTYPE).fields:
		if df.fieldtype == "Tab Break":
			open_tab(df.label, df.fieldname)
			continue
		if df.fieldtype == "Section Break":
			open_section(df.label, df.description, df.fieldname)
			continue
		if df.fieldtype in LAYOUT_FIELDTYPES or df.fieldtype in DISPLAY_FIELDTYPES:
			continue
		if section is None:
			open_section(None, None, "_section")
		if df.fieldtype in TABLE_FIELDTYPES:
			section["tables"].append(df.fieldname)
			continue
		section["fields"].append(describe(df))

	return tabs


def describe(df) -> dict:
	"""One control, as the page needs to draw it."""
	return {
		"fieldname": df.fieldname,
		"label": df.label or frappe.unscrub(df.fieldname),
		"fieldtype": df.fieldtype,
		"options": df.options,
		"description": df.description,
		"default": df.default,
		"depends_on": df.depends_on,
		"mandatory_depends_on": df.mandatory_depends_on,
		"read_only_depends_on": df.read_only_depends_on,
		"reqd": bool(df.reqd),
		"read_only": bool(df.read_only),
		"hidden": bool(df.hidden),
		# What a 0 in this box would mean. See zero_rule.
		"zero": zero_rule(df.fieldname),
		# True where a wrong value posts stock or money somewhere else rather
		# than raising.
		"posts": df.fieldname in POSTING_LINKS,
	}


def table_docfield(fieldname):
	"""The child-table field by name, or a throw naming what there is.

	A writer that trusted the caller's fieldname could point a delete at any
	child table on the site, so the name is resolved against the doctype's own
	tables rather than used.
	"""
	for df in table_docfields():
		if df.fieldname == fieldname:
			return df
	frappe.throw(
		_("{0} is not one of the lists on {1}.").format(fieldname or _("Nothing"), DOCTYPE)
	)


def table_columns(df):
	"""The editable columns of one child table."""
	return [
		cdf
		for cdf in frappe.get_meta(df.options).fields
		if cdf.fieldtype not in LAYOUT_FIELDTYPES
		and cdf.fieldtype not in DISPLAY_FIELDTYPES
		and cdf.fieldtype not in TABLE_FIELDTYPES
	]


def table_rows(df):
	"""One child table's rows as the page reads them, newest layout order."""
	doc = frappe.get_single(DOCTYPE)
	columns = table_columns(df)
	return [
		{
			"name": row.name,
			"idx": row.idx,
			**{c.fieldname: row.get(c.fieldname) for c in columns},
		}
		for row in doc.get(df.fieldname) or []
	]


def tables() -> list:
	"""The three child tables, with their rows.

	Read from the loaded Single rather than a `get_all` on the child doctype:
	child tables are not queryable on their own without naming the parent, and
	the parent is the thing this endpoint already guarded.
	"""
	doc = frappe.get_single(DOCTYPE)
	out = []
	for df in table_docfields():
		child_meta = frappe.get_meta(df.options)
		columns = [
			describe(cdf)
			for cdf in child_meta.fields
			if cdf.fieldtype not in LAYOUT_FIELDTYPES
			and cdf.fieldtype not in DISPLAY_FIELDTYPES
			and cdf.fieldtype not in TABLE_FIELDTYPES
		]
		rows = [
			{"name": row.name, "idx": row.idx,
			 **{c["fieldname"]: row.get(c["fieldname"]) for c in columns}}
			for row in doc.get(df.fieldname) or []
		]
		out.append(
			{
				"fieldname": df.fieldname,
				"fieldtype": df.fieldtype,
				"depends_on": df.depends_on,
				"read_only": bool(df.read_only),
				"label": df.label,
				"description": df.description,
				"doctype": df.options,
				"columns": columns,
				"rows": rows,
			}
		)
	return out


def write_table(df, sent):
	"""Replace one child table's rows. Shared by the one save endpoint and the
	older single-table one, so the two cannot drift.

	Coerces and checks the whole list before writing any of it, keeps the names
	of rows that survive, and never saves the parent (see
	`save_livestock_settings`). Returns `(added, removed)`.
	"""
	columns = table_columns(df)
	if not isinstance(sent, list):
		frappe.throw(_("The rows have to be a list."))

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
					_("Row {0} has no {1}.").format(position, cdf.label or frappe.unscrub(cdf.fieldname))
				)
			fields[cdf.fieldname] = value
		key = _table_key(columns, fields)
		if key is not None:
			# The same store listed twice counts its feed twice.
			if key in seen:
				frappe.throw(_("Row {0} is already on the list.").format(position))
			seen.add(key)
		wanted.append({"name": (row.get("name") or "").strip() or None, "idx": position, "fields": fields})

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
			frappe.db.set_value(df.options, want["name"], {**want["fields"], "idx": want["idx"]})
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
	return added, len(removed)


def _table_key(columns, fields):
	"""The first Link column makes a row the same row as another, or None."""
	for cdf in columns:
		if cdf.fieldtype == "Link":
			return fields.get(cdf.fieldname)
	return None
