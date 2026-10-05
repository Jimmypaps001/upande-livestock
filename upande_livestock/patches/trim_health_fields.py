# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Drop the health fields nothing kept, and date every case's milk withdrawal.

Read and written by nothing: on Livestock Health Case `lab_test_done`,
`lab_results`, `treatment_journal_entry`, `production_loss_value`,
`notification_reference`, and `vet_visit_date` / `linked_disposal`, which the
case file sent to a screen that never showed them; `milk_safe_date` on the
drug issue row (the case holds the date); `rumen_fill`, `confirmed_by_vet` and
`vet_name` on Livestock Diagnosis.

`milk_safe_date` on the case is now worked out from its treatments'
withdrawal periods. Existing cases are dated here, so the case file stops
showing "—" for every case already open.
"""

import frappe
from frappe.utils import add_days, getdate

from upande_livestock.patches._fold import append_lines, fold_into_notes, note_lines

DROPPED = {
	"Livestock Health Case": (
		"lab_test_done", "lab_results", "treatment_journal_entry", "production_loss_value",
		"notification_reference", "vet_visit_date", "linked_disposal",
	),
	"Livestock Drug Issue": ("milk_safe_date",),
	"Livestock Diagnosis": ("rumen_fill", "confirmed_by_vet", "vet_name"),
}


#: Where each doctype keeps what a dropped column said (live holds a lab
#: result, a vet visit date and a rumen-fill reading among them).
NOTES = {"Livestock Health Case": "outcome_notes", "Livestock Diagnosis": "action_notes"}
LABELS = {
	"lab_test_done": "Lab test done", "lab_results": "Lab results",
	"treatment_journal_entry": "Treatment journal entry",
	"production_loss_value": "Production loss value",
	"notification_reference": "Notification reference", "vet_visit_date": "Vet visit",
	"linked_disposal": "Disposal", "rumen_fill": "Rumen fill",
	"confirmed_by_vet": "Confirmed by vet", "vet_name": "Vet",
}
#: A drug row's milk-safe date goes onto its parent's notes.
PARENT_NOTES = {"Livestock Event": "remarks", "Livestock Diagnosis": "action_notes"}


def fold_drug_row_dates():
	if not frappe.db.has_column("Livestock Drug Issue", "milk_safe_date"):
		return
	for row in frappe.db.sql(
		"""SELECT parent, parenttype, item_code, milk_safe_date
		   FROM `tabLivestock Drug Issue` WHERE milk_safe_date IS NOT NULL""",
		as_dict=True,
	):
		field = PARENT_NOTES.get(row.parenttype)
		if not field or not frappe.db.exists(row.parenttype, row.parent):
			continue
		current = frappe.db.get_value(row.parenttype, row.parent, field)
		line = note_lines({"d": row.milk_safe_date}, {"d": f"Milk safe from ({row.item_code})"})
		append_lines(row.parenttype, row.parent, field, current, line)


def execute():
	for doctype, field in NOTES.items():
		fold_into_notes(doctype, {c: LABELS[c] for c in DROPPED[doctype]}, field)
	fold_drug_row_dates()
	for doctype, fields in DROPPED.items():
		frappe.db.delete("Property Setter", {"doc_type": doctype, "field_name": ("in", fields)})
		frappe.clear_cache(doctype=doctype)
		for column in fields:
			if frappe.db.has_column(doctype, column):
				frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{column}`")

	ends = {}
	for row in frappe.db.sql(
		"""SELECT parent, treatment_date, withdrawal_period_days
		   FROM `tabLivestock Health Treatment`
		   WHERE parenttype = 'Livestock Health Case'
		     AND treatment_date IS NOT NULL AND IFNULL(withdrawal_period_days, 0) > 0""",
		as_dict=True,
	):
		end = add_days(getdate(row.treatment_date), int(row.withdrawal_period_days))
		ends[row.parent] = max(end, ends.get(row.parent, end))
	for case, end in ends.items():
		frappe.db.set_value("Livestock Health Case", case, "milk_safe_date", end, update_modified=False)
