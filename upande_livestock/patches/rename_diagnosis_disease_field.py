# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Rename Livestock Diagnosis.suggested_diagnosis to suggested_disease.

The field links Livestock Disease, so "disease" is what it holds. 3 documents on
kaitet.local. Idempotent: guarded on the old column still existing.
"""

import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	if not frappe.db.table_exists("Livestock Diagnosis"):
		return
	if not frappe.db.has_column("Livestock Diagnosis", "suggested_diagnosis"):
		return

	rename_field("Livestock Diagnosis", "suggested_diagnosis", "suggested_disease")
	frappe.db.commit()
