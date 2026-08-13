# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Fold per-event activity cost into remarks before the fields are removed.

32 events on kaitet.local carry a non-zero custom_activity_cost (KES 3,772.21
total). Frappe does not drop orphaned columns on migrate, so the raw values stay
readable in SQL — this patch makes them visible in the UI instead.

Runs in [pre_model_sync], while the accounting fields are still on the DocType.
"""

import frappe
from frappe.utils import flt, fmt_money

MARKER = "[migrated] Activity cost"


def execute():
	if not frappe.db.table_exists("Livestock Event"):
		return
	if not frappe.db.has_column("Livestock Event", "custom_activity_cost"):
		return

	rows = frappe.db.sql(
		"""SELECT name, remarks, custom_activity_cost, custom_expense_account,
		          custom_cost_center, custom_journal_entry
		   FROM `tabLivestock Event`
		   WHERE IFNULL(custom_activity_cost, 0) > 0""",
		as_dict=True,
	)

	for row in rows:
		if MARKER in (row.remarks or ""):
			continue

		note = "{marker} {amount} · Expense: {expense} · Cost Center: {cc} · JE: {je}".format(
			marker=MARKER,
			amount=fmt_money(flt(row.custom_activity_cost), currency="KES"),
			expense=row.custom_expense_account or "—",
			cc=row.custom_cost_center or "—",
			je=row.custom_journal_entry or "—",
		)
		remarks = f"{row.remarks}\n{note}" if row.remarks else note
		frappe.db.set_value("Livestock Event", row.name, "remarks", remarks, update_modified=False)

	frappe.db.commit()
	print(f"Preserved activity cost on {len(rows)} Livestock Event documents")
