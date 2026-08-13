# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Rename Livestock Diagnosis.suggested_diagnosis to suggested_disease.

The field links Livestock Disease, so "disease" is what it holds. 3 documents on
kaitet.local, all NULL/NULL on both columns today.

Deliberately does NOT call frappe.model.utils.rename_field(). That helper does
two things: (1) an unconditional `UPDATE ... SET new = old` over every row, and
(2) ancillary renames of anything else that names the old fieldname — Report
column configs, Property Setters, Custom Fields, saved list-view/report-view
settings, and password-field storage for the doctype. (1) is exactly the bug
this patch used to have: Frappe never drops the renamed-from column
(has_column("suggested_diagnosis") stays true forever), so a schema-based
guard is permanently true and every future migrate would re-run that blanket
UPDATE, overwriting any value entered into suggested_disease since the first
run with whatever (possibly NULL, possibly stale) value still sits in the
orphaned old column.

(2) was checked before dropping it, not assumed away: on this site there are
zero rows in tabProperty Setter and zero in tabCustom Field (both tables exist
with no rows — never populated), no Report references suggested_diagnosis
(tabReport has no reference_doctype column on this Frappe version to even
query, and a source grep across the app's shipped fixtures/reports/doctype
JSON turns up nothing), and the only shipped custom_field.json fixture targets
Stock Entry, not Livestock Diagnosis. So skipping rename_field's ancillary
work is safe here and, per the same reasoning, on any other site running this
app version — none of them ship a Report, Property Setter or Custom Field
naming this field either. If a future patch or fixture ever does reference
suggested_diagnosis, that dependency must be re-checked before continuing to
skip rename_field.

Idempotent by construction, not by a whole-table "has this run before" flag:
the UPDATE below only ever touches a row that still holds a real value in the
old column AND has never received one in the new column. A row already
migrated, or a row a user has since edited directly, is never touched again —
regardless of how many times this patch re-runs, and regardless of what the
current 0-record, NULL/NULL state on this site happens to look like right now
(which cannot meaningfully answer "has the rename already happened" either
way — see test_rename_diagnosis_disease_field.py for why a whole-table guard
was rejected in favour of this).
"""

import frappe


def execute():
	if not frappe.db.table_exists("Livestock Diagnosis"):
		return
	if not frappe.db.has_column("Livestock Diagnosis", "suggested_diagnosis"):
		return
	if not frappe.db.has_column("Livestock Diagnosis", "suggested_disease"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabLivestock Diagnosis`
		SET suggested_disease = suggested_diagnosis
		WHERE suggested_diagnosis IS NOT NULL AND suggested_diagnosis != ''
		  AND (suggested_disease IS NULL OR suggested_disease = '')
		"""
	)
	frappe.db.commit()
