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
		"drug_warehouse",
		"semen_warehouse",
		"semen_item",
		"custom_default_company",
		"custom_default_credit_account",
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
	"""The only fieldnames a write is allowed to name."""
	return frozenset(df.fieldname for df in scalar_docfields())


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
		"reqd": bool(df.reqd),
		# What a 0 in this box would mean. See zero_rule.
		"zero": zero_rule(df.fieldname),
		# True where a wrong value posts stock or money somewhere else rather
		# than raising.
		"posts": df.fieldname in POSTING_LINKS,
	}


def tables() -> list:
	"""The three child tables, with their rows, for display only.

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
		rows = []
		for row in doc.get(df.fieldname) or []:
			rows.append({"idx": row.idx, **{c["fieldname"]: row.get(c["fieldname"]) for c in columns}})
		out.append(
			{
				"fieldname": df.fieldname,
				"label": df.label,
				"description": df.description,
				"doctype": df.options,
				"columns": columns,
				"rows": rows,
			}
		)
	return out
