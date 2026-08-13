# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Rename Livestock Event documents to TYPE-YEAR-#####.

Live data was named {animal}-{event_type}-{seq}, e.g.
ABIGEAL-129257-Vaccination-1736472. The animal is already a field on the
document, so it does not belong in the name.

Runs in [post_model_sync]: event_type must already be a Link, and every value
must have a Livestock Event Type record, which is why the seeder is called first.
"""

import re

import frappe
from frappe.model.naming import make_autoname
from frappe.model.rename_doc import rename_doc
from frappe.utils import getdate, nowdate

from upande_livestock.install import ensure_livestock_event_types

NEW_NAME_RE = re.compile(r"^[A-Z0-9-]+-\d{4}-\d{5}$")


def build_name(event_type, event_date):
	prefix = re.sub(r"[^A-Z0-9]+", "-", (event_type or "").upper()).strip("-")
	year = getdate(event_date or nowdate()).year
	return make_autoname(f"{prefix}-{year}-.#####")


def execute():
	ensure_livestock_event_types()

	rows = frappe.db.sql(
		"""SELECT name, event_type, event_date
		   FROM `tabLivestock Event`
		   ORDER BY IFNULL(event_date, creation), creation""",
		as_dict=True,
	)

	renamed = 0
	for row in rows:
		if NEW_NAME_RE.match(row.name):
			continue
		if not row.event_type:
			frappe.log_error(
				message=f"Livestock Event {row.name} has no event_type; not renamed.",
				title="Livestock event rename skipped",
			)
			continue
		try:
			# frappe.rename_doc (the top-level wrapper) has no ignore_permissions
			# parameter on Frappe 16.26.3 — only the inner frappe.model.rename_doc
			# does. Confirmed in Task 1.
			rename_doc(
				doctype="Livestock Event",
				old=row.name,
				new=build_name(row.event_type, row.event_date),
				force=True,
				ignore_permissions=True,
				show_alert=False,
			)
			renamed += 1
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Livestock event rename failed: {row.name}",
			)

	frappe.db.commit()
	print(f"Renamed {renamed} Livestock Event documents")
