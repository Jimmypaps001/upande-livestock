# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The beef app does not milk. Remove what a dairy install left behind.

Refuses, rather than discards, when a submitted Milk Recording or a submitted
Milking Stock Entry exists: those are ledger history someone has to decide on.
A no-op on a site that never had any of it.
"""

import frappe

MILK_DOCTYPES = ("Milk Recording", "Livestock Milking Herd")
EVENT_TYPES = ("Milking", "Drying Off")
MILKER_ROLE = "Livestock Milker"

# Livestock Settings values that only the milking side read.
SETTINGS_DROPPED = (
	"custom_milk_item",
	"custom_milking_stock_entry_type",
	"custom_milk_target_warehouse",
	"custom_milk_discard_warehouse",
	"custom_milk_business_unit",
	"custom_milk_income_account",
	"custom_default_milk_price",
	"custom_milk_price_per_kg",
	"allow_offline_milking_grace",
	"custom_milk_quality_capture",
	"custom_quality_required_at_milking",
	"custom_quality_required_in_lab",
	"custom_quality_scc_ceiling",
	"custom_target_prod_group1",
	"custom_target_prod_group2",
	"custom_target_prod_group3",
	"custom_target_prod_average",
	"custom_target_mafc_group1",
	"custom_target_mafc_group2",
	"custom_target_mafc_group3",
	"custom_target_dim",
	"custom_target_preg_100dim",
	"custom_target_not_preg_200dim",
	"high_yield_herd",
	"low_yield_herd",
	"post_calving_herd",
	"high_yield_days_from_conception",
	"low_yield_days",
	"drying_off_herd",
	"steamer_herd",
	"steamer_days_from_heifers",
	"steamer_days_from_lactation",
	"heifer_dry_off_before_calving_days",
)


def _is_milk_field(fieldname):
	return fieldname.startswith(("custom_milk", "custom_milking")) or fieldname == "custom_cows_milked"


def _refuse_if_ledger_history():
	problems = []
	if frappe.db.table_exists("Milk Recording"):
		n = frappe.db.sql("select count(*) from `tabMilk Recording` where docstatus = 1")[0][0]
		if n:
			problems.append(f"{n} submitted Milk Recording(s)")
	if frappe.db.exists("Stock Entry Type", "Milking"):
		n = frappe.db.count("Stock Entry", {"stock_entry_type": "Milking", "docstatus": 1})
		if n:
			problems.append(f"{n} submitted Stock Entry(ies) of type Milking")
	if problems:
		frappe.throw(
			"Cannot remove milking: " + " and ".join(problems) + " exist. "
			"Cancel or archive them first.",
			frappe.ValidationError,
		)


def _carry_withdrawal_dates():
	"""Milk withdrawal on a case becomes the date it may go to slaughter.

	The treatments' withdrawal days are the same figure either way; only the
	name of what they gate changed. Cases that already hold a date keep it.
	"""
	table = "tabLivestock Health Case"
	if not frappe.db.has_column("Livestock Health Case", "milk_safe_date"):
		return
	if frappe.db.has_column("Livestock Health Case", "slaughter_safe_date"):
		frappe.db.sql(
			f"update `{table}` set slaughter_safe_date = milk_safe_date "
			"where slaughter_safe_date is null and milk_safe_date is not null"
		)
	frappe.db.sql_ddl(f"alter table `{table}` drop column milk_safe_date")


def _drop_desk_entries():
	"""Frappe re-ships a workspace's links but never removes the ones it stopped shipping."""
	for doctype in ("Workspace Shortcut", "Workspace Link", "Workspace Sidebar Item"):
		if frappe.db.table_exists(doctype):
			frappe.db.delete(doctype, {"link_to": ["in", list(MILK_DOCTYPES)]})
	if frappe.db.table_exists("Workspace Sidebar Item"):
		frappe.db.delete("Workspace Sidebar Item", {"parent": "Livestock", "label": "Production"})
	frappe.db.sql(
		"update `tabWorkspace` set icon = 'paw-print' where name = 'Livestock' and icon = 'milk'"
	)


def execute():
	_refuse_if_ledger_history()

	for dt in MILK_DOCTYPES:
		if frappe.db.exists("DocType", dt):
			frappe.delete_doc("DocType", dt, force=True)

	for name in EVENT_TYPES:
		# Livestock Event Type may not exist on every install; delete_doc tolerates it.
		for doctype in ("Livestock Event Type", "Stock Entry Type"):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_missing=True)

	for cf in frappe.get_all("Custom Field", fields=["name", "dt", "fieldname"]):
		if _is_milk_field(cf.fieldname):
			frappe.db.delete("Property Setter", {"doc_type": cf.dt, "field_name": cf.fieldname})
			frappe.delete_doc("Custom Field", cf.name, force=True, ignore_missing=True)

	frappe.db.delete("Has Role", {"role": MILKER_ROLE})
	frappe.db.delete("Custom DocPerm", {"role": MILKER_ROLE})
	if frappe.db.exists("Role", MILKER_ROLE):
		frappe.delete_doc("Role", MILKER_ROLE, force=True, ignore_missing=True)

	for fieldname in SETTINGS_DROPPED:
		frappe.db.delete("Singles", {"doctype": "Livestock Settings", "field": fieldname})

	_carry_withdrawal_dates()
	_drop_desk_entries()

	# A table can outlive its DocType row if an earlier run was interrupted.
	for dt in MILK_DOCTYPES:
		frappe.db.sql_ddl(f"drop table if exists `tab{dt}`")

	frappe.clear_cache()
