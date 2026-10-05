# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Carry the old Animal Event's custom fields into Livestock Event, then remove them.

The live site still runs the first design of the event form: some thirty-five
Custom Field records on "Animal Event", which the rename carries onto
Livestock Event intact. Nothing in the app reads them, and several hold real
history — 136 vaccine names, 27 dosages, 25 weights, 22 body condition scores,
the herd 14 movements went to. Left alone they would sit on the form as a
second set of boxes, and their values would be invisible to every screen.

Each value goes to the place the current design keeps it:

  * a field with a standard twin is copied into it, where the twin is empty
    (the herd moved from and to, the semen straw, the dam, the issue entry,
    and on a Birth the calf's tag, name, sex, weight and herd);
  * a weight recorded on a Weight Recording event becomes a submitted
    Livestock Weight Record, oldest first, so her weight history and
    `last_weight_kg` come out right;
  * the drugs table moves onto the standard one: its rows already have the
    same columns, only the table field name differs;
  * what has no structured home (a vaccine typed by name, its dose, batch and
    withdrawal, a next-due date, coat colour) is written into the event's
    remarks as "[migrated] <Label>: <value>".

Then those Custom Fields (LEGACY, named exactly) are deleted and their
columns dropped. Not copied: `custom_animal_ref`, which on
the live site never names an animal `animal` does not; `custom_calf_outcome`,
which carries only its first option on every row; the accounting fields,
which preserve_event_activity_cost already folded; and `workflow_state`, whose
workflow is inactive.
"""

import frappe
from frappe.utils import flt

from upande_livestock.patches._fold import append_lines, column_exists, drop_column, note_lines

DT = "Livestock Event"

#: legacy column -> (standard column, the event types it applies to; None = all)
COPY = {
	"custom_from_herd": ("current_herd", None),
	"custom_to_herd": ("new_herd", None),
	"custom_semen_item": ("semen_item", ("Service",)),
	"custom_dam_animal": ("dam", None),
	"custom_material_issue_entry": ("stock_entry", None),
	"custom_calf_book_number": ("calf_tag_number", ("Birth",)),
	"custom_calf_burn_name": ("calf_burn_name", ("Birth",)),
	"custom_calf_gender": ("calf_sex", ("Birth",)),
	"custom_calf_birth_weight_kg": ("calf_birth_weight_kg", ("Birth",)),
	"custom_calf_target_herd": ("calf_herd", ("Birth",)),
}

#: legacy column -> label, written into remarks
FOLD = {
	"custom_vaccine_drug_name": "Vaccine / drug",
	"custom_dosage": "Dosage",
	"custom_batch_no": "Batch",
	"custom_withdrawal_period_days": "Withdrawal (days)",
	"custom_next_due_date": "Next due",
	"custom_birth_weight_kg": "Birth weight (kg)",
	"custom_calf_coat_colour": "Calf coat colour",
	"custom_created_animal": "Animal created",
	"custom_calf_animal_created": "Calf animal created",
	"custom_sire_catalog": "Sire (catalogue)",
}

#: The calf columns, kept in remarks on the events where they have no twin.
CALF_LABELS = {
	"custom_calf_book_number": "Calf tag",
	"custom_calf_burn_name": "Calf name",
	"custom_calf_gender": "Calf sex",
	"custom_calf_birth_weight_kg": "Calf birth weight (kg)",
	"custom_calf_target_herd": "Calf herd",
}


def execute():
	if not frappe.db.table_exists(DT):
		return
	drop_duplicate_declarations()
	legacy = legacy_fields()
	if not legacy:
		return
	repoint_drug_rows()
	copy_into_standard_fields()
	weights_kept = weight_records_from_events()
	fold_into_remarks(weights_kept)
	remove(legacy)


#: The first design's 54 Custom Fields, exactly as the live site held them on
#: 2026-10-05 (breaks included). Named, not inferred: a field somebody adds
#: on purpose before this runs is not this patch's to remove.
LEGACY = (
	"custom_activity_cost",
	"custom_animal_ref",
	"custom_basic_section",
	"custom_batch_no",
	"custom_bcs",
	"custom_birth_weight_kg",
	"custom_calf_animal_created",
	"custom_calf_birth_weight_kg",
	"custom_calf_book_number",
	"custom_calf_burn_name",
	"custom_calf_coat_colour",
	"custom_calf_gender",
	"custom_calf_outcome",
	"custom_calf_sex",
	"custom_calf_target_herd",
	"custom_calving_outcome",
	"custom_calving_section",
	"custom_col_break_basic",
	"custom_col_break_calving",
	"custom_col_break_cost",
	"custom_col_break_diagnosis",
	"custom_col_break_movement",
	"custom_col_break_service",
	"custom_col_break_vaccination",
	"custom_cost_center",
	"custom_cost_section",
	"custom_cost_tab",
	"custom_created_animal",
	"custom_dam_animal",
	"custom_diagnosis_section",
	"custom_dosage",
	"custom_drug_issues",
	"custom_dryoff_section",
	"custom_event_info_tab",
	"custom_expense_account",
	"custom_from_herd",
	"custom_health_tab",
	"custom_journal_entry",
	"custom_material_issue_entry",
	"custom_movement_section",
	"custom_next_due_date",
	"custom_no_of_calves",
	"custom_related_pregnancy",
	"custom_semen_item",
	"custom_service_section",
	"custom_sire_catalog",
	"custom_status_after_test",
	"custom_to_herd",
	"custom_vaccination_section",
	"custom_vaccine_drug_name",
	"custom_weight",
	"custom_weight_section",
	"custom_withdrawal_period_days",
	"workflow_state",
)


def drop_duplicate_declarations():
	"""A legacy Custom Field the doctype now declares itself (the calving
	outcome, the number of calves, the related pregnancy) is the same field
	declared twice. The record goes; the column, and its data, stay."""
	standard = set(frappe.get_all("DocField", filters={"parent": DT}, pluck="fieldname"))
	frappe.db.delete("Custom Field", {"dt": DT, "fieldname": ("in", [n for n in LEGACY if n in standard])})


def legacy_fields():
	"""Those of LEGACY still present as Custom Fields the doctype does not declare."""
	standard = set(frappe.get_all("DocField", filters={"parent": DT}, pluck="fieldname"))
	return frappe.get_all(
		"Custom Field",
		filters={"dt": DT, "fieldname": ["in", [n for n in LEGACY if n not in standard]]},
		fields=["name", "fieldname", "fieldtype"],
	)


def has(column):
	return column_exists(DT, column)


def repoint_drug_rows():
	frappe.db.sql(
		"""UPDATE `tabLivestock Drug Issue` SET parentfield = 'drug_issues'
		   WHERE parenttype = %s AND parentfield = 'custom_drug_issues'""",
		(DT,),
	)


def copy_into_standard_fields():
	for old, (new, types) in COPY.items():
		if not (has(old) and has(new)):
			continue
		where = "AND event_type IN %(types)s" if types else ""
		frappe.db.sql(
			f"""UPDATE `tab{DT}` SET `{new}` = `{old}`
			    WHERE IFNULL(`{old}`, '') NOT IN ('', '0') AND IFNULL(`{new}`, '') IN ('', '0') {where}""",
			{"types": types or ()},
		)


def weight_records_from_events():
	"""Turn each recorded weight into a Livestock Weight Record. Returns the
	events whose weight now lives on a record, so it is not also written into
	remarks."""
	if not has("custom_weight"):
		return set()
	bcs = "custom_bcs" if has("custom_bcs") else "NULL"
	kept = set()
	for row in frappe.db.sql(
		f"""SELECT e.name, e.animal, e.event_date, e.custom_weight AS weight, {bcs} AS bcs
		    FROM `tab{DT}` e JOIN `tabAnimal` a ON a.name = e.animal
		    WHERE e.event_type = 'Weight Recording' AND e.docstatus = 1
		      AND IFNULL(e.custom_weight, 0) > 0 AND e.event_date IS NOT NULL
		    ORDER BY e.event_date ASC, e.creation ASC""",
		as_dict=True,
	):
		if frappe.db.exists("Livestock Weight Record",
		                    {"animal": row.animal, "weight_date": row.event_date, "docstatus": 1}):
			kept.add(row.name)
			continue
		try:
			record = frappe.get_doc({
				"doctype": "Livestock Weight Record",
				"animal": row.animal,
				"weight_date": row.event_date,
				"weight_kg": flt(row.weight),
				"bcs": flt(row.bcs) or None,
				"remarks": f"Migrated from {row.name}",
			})
			record.flags.ignore_permissions = True
			record.insert(ignore_permissions=True)
			record.submit()
			kept.add(row.name)
		except Exception:
			frappe.log_error(title=f"Weight from {row.name} not migrated; kept in its remarks")
	return kept


def fold_into_remarks(weights_kept):
	labels = {c: l for c, l in FOLD.items() if has(c)}
	calf = {c: l for c, l in CALF_LABELS.items() if has(c)}
	weight = {c: l for c, l in {"custom_weight": "Weight (kg)", "custom_bcs": "BCS"}.items() if has(c)}
	columns = sorted(set(labels) | set(calf) | set(weight))
	if not columns:
		return
	select = ", ".join(f"`{c}`" for c in columns)
	for row in frappe.db.sql(
		f"SELECT name, event_type, remarks, {select} FROM `tab{DT}`", as_dict=True
	):
		lines = note_lines(row, labels)
		if row.event_type != "Birth":
			lines += note_lines(row, calf)
		if row.name not in weights_kept:
			lines += note_lines(row, weight)
		append_lines(DT, row.name, "remarks", row.remarks, lines)


def remove(legacy):
	names = [f.fieldname for f in legacy]
	frappe.db.delete("Custom Field", {"name": ("in", [f.name for f in legacy])})
	frappe.db.delete("Property Setter", {"doc_type": DT, "field_name": ("in", names)})
	frappe.clear_cache(doctype=DT)
	for f in legacy:
		if f.fieldtype not in ("Table", "Table MultiSelect"):
			drop_column(DT, f.fieldname)
