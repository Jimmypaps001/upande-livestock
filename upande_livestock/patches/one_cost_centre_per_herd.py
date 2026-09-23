# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Fold the herd's two cost-centre fields into one, and carry the setting over.

Herds shipped `cost_center` AND `custom_cost_center`, both fieldtype Link to
Cost Center, both labelled "Cost Center", sitting in the same Accounting
section. Nothing read either for feed, milk or drugs, so the divergence went
unnoticed: on the live site `custom_cost_center` is empty on every herd, while
on an older site the same herd held `Main - WDL` in one and `WestwoodDairies
Ltd - WDL` in the other. "The herd's cost centre" had two answers.

`cost_center` is the survivor — it is the populated one (nine of eleven live
herds name `Dairy - KR`), and the one `milking_options` already reads. The
custom twin's value is carried across first, so a site that filled in only that
one keeps what it configured.

The flat `Livestock Settings.custom_default_cost_center` goes the same way,
into a per-company row: this group runs a dairy and a flower business under one
company list, and a single site-wide centre charged both to whichever one was
set. Its value becomes the row for the default company, which is exactly what
it meant.

Nothing is invented. A herd with neither field set stays blank and falls to the
settings row, which announces itself — see serverscripts/common/cost_center.
"""

import frappe

SETTINGS = "Livestock Settings"
TABLE = "custom_company_cost_centers"


def execute():
	carry_the_herds_custom_field_across()
	carry_the_flat_setting_into_a_company_row()
	frappe.clear_cache()


def carry_the_herds_custom_field_across():
	"""`custom_cost_center` -> `cost_center`, only where the survivor is blank.

	Column-level, because the field is gone from the DocType by the time this
	runs and `get_all` would not return it. A site that never had the custom
	twin has no column and nothing to do.
	"""
	if not frappe.db.has_column("Herds", "custom_cost_center"):
		return
	if not frappe.db.has_column("Herds", "cost_center"):
		return

	rows = frappe.db.sql(
		"""SELECT name, custom_cost_center
		   FROM `tabHerds`
		   WHERE IFNULL(custom_cost_center, '') <> ''
		     AND IFNULL(cost_center, '') = ''""",
		as_dict=True,
	)
	for row in rows:
		frappe.db.set_value(
			"Herds", row.name, "cost_center", row.custom_cost_center, update_modified=False
		)


def carry_the_flat_setting_into_a_company_row():
	"""The old site-wide default becomes the row for the default company."""
	if not frappe.db.has_column("tabSingles", "value"):  # pragma: no cover - sanity
		return
	old = frappe.db.get_value(
		"Singles", {"doctype": SETTINGS, "field": "custom_default_cost_center"}, "value"
	)
	if not old:
		return

	company = frappe.db.get_single_value(SETTINGS, "custom_default_company")
	if not company:
		return

	settings = frappe.get_single(SETTINGS)
	if not settings.meta.has_field(TABLE):
		return
	if any(r.company == company for r in settings.get(TABLE) or []):
		return

	settings.append(TABLE, {"company": company, "cost_center": old})
	settings.save(ignore_permissions=True)
