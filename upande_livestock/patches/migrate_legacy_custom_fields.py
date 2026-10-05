# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Carry the live site's leftover Custom Fields on the other doctypes into the
current design, then remove them. migrate_legacy_event_fields does Livestock
Event; this does the rest, from what the live site held on 2026-10-05.

Livestock Settings. Five settings the code now reads under another name are
copied across where the new one is empty — the drug store above all: live
keeps its drugs in "Drug/ Medicine store- old office - KR" under
`custom_drug_warehouse`, and the code reads `drug_warehouse`, so without this
every issue on live would look for drugs in no store at all. Seven fields the
doctype already declared, and the 37 the farm chose to keep (accounts,
business units, farm, production and fertility targets, milk price,
colostrum and weaning — now fields of the doctype), lose only their duplicate
Custom Field record; every value stays. The Journal Entry box, which drove
activity-cost entries that no longer exist, is dropped.

Livestock Weight Record. On live this was a child table of Animal: its eight
rows name their animal as `parent` and their date as `recording_date`. Each
becomes a submitted record of its own, oldest first, so the animal's weight
history and last weight come out right.

Livestock Disposal, Milk Recording, Livestock Insurance Policy. Fields nothing
reads, kept in each record's notes where they hold anything, then dropped.
"""

import frappe

from upande_livestock.patches._fold import column_exists, drop_column, fold_into_notes

SETTINGS = "Livestock Settings"

#: old setting -> the setting the code reads now
SETTING_RENAMES = {
	"custom_drug_warehouse": "drug_warehouse",
	"custom_semen_warehouse": "semen_warehouse",
	"custom_default_heifer_herd": "female_calf_herd",
	"custom_default_bull_herd": "male_calf_herd",
	"custom_default_dry_herd": "steamer_herd",
}

#: Custom Fields that the doctypes now declare themselves. Record goes, data stays.
DECLARED = {
	SETTINGS: (
		"custom_default_company", "custom_default_credit_account", "custom_milk_item",
		"custom_milk_target_warehouse", "custom_milk_discard_warehouse",
		"custom_milking_stock_entry_type", "custom_feed_wip_warehouse",
		# Kept at the farm's request: accounts, business units, farm, targets,
		# milk price, colostrum and weaning. Now declared by the doctype.
		"custom_farm",
		"custom_si_farm",
		"custom_disposal_farm",
		"custom_disposal_business_unit",
		"custom_animal_sale_item",
		"custom_insurance_receivable_account",
		"custom_insurance_income_account",
		"custom_disposal_account",
		"custom_default_payout_percent",
		"custom_default_milk_price",
		"custom_colostrum_item",
		"custom_milk_price_per_kg",
		"custom_colostrum_warehouse",
		"custom_milk_business_unit",
		"custom_colostrum_day1_pct_of_birth_weight",
		"custom_colostrum_days2to5_pct_of_body_weight",
		"custom_milk_feeding_pct_of_body_weight",
		"custom_weaning_start_day",
		"custom_weaning_complete_day",
		"custom_target_prod_group1",
		"custom_target_prod_group2",
		"custom_target_prod_group3",
		"custom_target_prod_average",
		"custom_target_mafc_group1",
		"custom_target_mafc_group2",
		"custom_target_mafc_group3",
		"custom_target_dim",
		"custom_target_calving_interval",
		"custom_target_first_insem",
		"custom_target_days_open",
		"custom_target_straws_per_preg",
		"custom_target_preg_100dim",
		"custom_target_not_preg_200dim",
		"custom_target_growth_gday",
		"custom_animal_asset_account",
		"custom_animal_sale_income_account",
		"custom_vet_expense_account",
		"custom_feed_expense_account",
		"custom_milk_income_account",
	),
	"Livestock Disposal": ("sales_invoice",),
	"Livestock Weight Record": ("weight_kg", "bcs"),
}

#: Settings dropped outright. The Journal Entry box drove the activity-cost
#: entries, which no longer exist; the layout breaks belonged to the old form.
SETTINGS_DROPPED = ("custom_auto_create_journal_entry",) + (
	"custom_accounting_tab",
	"custom_defaults_section",
	"custom_col_break_accounting",
	"custom_insurance_section",
	"custom_col_break_insurance",
	"custom_livestock_accounts_section",
	"custom_milk_production_section",
	"custom_col_break_milk",
	"custom_kpi_targets_tab",
	"custom_production_targets_section",
	"custom_col_break_prod_targets",
	"custom_fertility_targets_section",
	"custom_col_break_fertility",
	"custom_youngstock_targets_section",
)

#: doctype -> (notes field, {column: label}, where) for the orphans folded then dropped
FOLDED = {
	"Livestock Disposal": ("reason_details", {
		"insurance_policy": "Insurance policy", "insured_value": "Insured value",
		"insurance_claim_amount": "Claim amount", "payment_entry": "Payment entry",
	}, None),
	"Milk Recording": ("remarks", {
		"is_colostrum": "Colostrum", "colostrum_yield_kg": "Colostrum (kg)",
		"colostrum_stock_entry": "Colostrum stock entry",
	}, None),
	"Livestock Insurance Policy": ("remarks", {
		"custom_insurer_supplier": "Insurer (supplier)", "custom_insurer_customer": "Insurer (customer)",
	}, None),
	"Livestock Weight Record": ("remarks", {
		"daily_gain_g": "Daily gain (g)", "event_ref": "Recorded on event",
	}, None),
}

#: Folded only where it meant something: payout % defaulted onto every disposal.
PAYOUT = ("Livestock Disposal", {"payout_percent": "Payout %"}, "reason_details",
          "IFNULL(insurance_policy, '') <> ''")

#: Weight Record columns of the child-table design, dropped once read.
WEIGHT_CHILD_COLUMNS = ("recording_date",)


def execute():
	carry_settings_across()
	weight_rows_into_records()
	for doctype, (notes, labels, where) in FOLDED.items():
		fold_into_notes(doctype, labels, notes, where)
	fold_into_notes(*PAYOUT)
	for doctype, fields in DECLARED.items():
		frappe.db.delete("Custom Field", {"dt": doctype, "fieldname": ("in", fields)})
	drop(SETTINGS, list(SETTING_RENAMES) + list(SETTINGS_DROPPED), single=True)
	for doctype, (_notes, labels, _where) in FOLDED.items():
		extra = ["payout_percent"] if doctype == "Livestock Disposal" else []
		extra += list(WEIGHT_CHILD_COLUMNS) if doctype == "Livestock Weight Record" else []
		drop(doctype, list(labels) + extra)


def _single(field):
	rows = frappe.db.sql(
		"SELECT `value` FROM `tabSingles` WHERE doctype = %s AND field = %s", (SETTINGS, field)
	)
	return rows[0][0] if rows else None


def carry_settings_across():
	for old, new in SETTING_RENAMES.items():
		value = _single(old)
		if value and not _single(new):
			frappe.db.set_single_value(SETTINGS, new, value)


def weight_rows_into_records():
	"""The child-table weight rows, made records of their own."""
	doctype = "Livestock Weight Record"
	if not (column_exists(doctype, "recording_date") and column_exists(doctype, "parent")):
		return
	rows = frappe.db.sql(
		f"""SELECT name, parent, recording_date FROM `tab{doctype}`
		    WHERE parenttype = 'Animal' AND IFNULL(animal, '') = ''
		    ORDER BY recording_date ASC, creation ASC""",
		as_dict=True,
	)
	for row in rows:
		frappe.db.sql(
			f"""UPDATE `tab{doctype}`
			    SET animal = %s, weight_date = IFNULL(weight_date, %s),
			        parent = NULL, parentfield = NULL, parenttype = NULL
			    WHERE name = %s""",
			(row.parent, row.recording_date, row.name),
		)
	for row in rows:
		try:
			record = frappe.get_doc(doctype, row.name)
			if record.docstatus == 0 and record.weight_date and frappe.db.exists("Animal", record.animal):
				record.flags.ignore_permissions = True
				record.submit()
		except Exception:
			frappe.log_error(title=f"Weight record {row.name} left in draft by the migration")


def drop(doctype, fields, single=False):
	frappe.db.delete("Custom Field", {"dt": doctype, "fieldname": ("in", fields)})
	frappe.db.delete("Property Setter", {"doc_type": doctype, "field_name": ("in", fields)})
	frappe.clear_cache(doctype=doctype)
	if single:
		frappe.db.delete("Singles", {"doctype": doctype, "field": ("in", fields)})
		return
	for field in fields:
		drop_column(doctype, field)
