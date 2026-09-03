# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Create timeline events for health records submitted before the timeline existed.

sync_event_for is idempotent (it updates the document's existing event rather
than creating a second one), so this patch is safe to re-run.
"""

import frappe

from upande_livestock.install import ensure_livestock_event_types
from upande_livestock.serverscripts.common.event_link import sync_event_for

BACKFILL = (
	("Livestock Diagnosis", "Check Up"),
	("Livestock Health Case", "Health Case"),
)


def execute():
	ensure_livestock_event_types()

	created = 0
	for doctype, event_type in BACKFILL:
		if not frappe.db.table_exists(doctype):
			continue
		for name in frappe.db.get_all(doctype, filters={"docstatus": 1}, pluck="name"):
			try:
				doc = frappe.get_doc(doctype, name)
				if not doc.animal:
					continue
				sync_event_for(doc, event_type)
				created += 1
			except Exception:
				frappe.log_error(
					message=frappe.get_traceback(),
					title=f"Health timeline backfill failed: {doctype} {name}",
				)

	frappe.db.commit()
	print(f"Backfilled timeline events for {created} health records")
