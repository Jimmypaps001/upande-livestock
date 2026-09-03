# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Align event_date with service_date / diagnosis_date where the two disagree.

Distinct from the sibling patch backfill_event_date_from_twin_field, which only
fills rows where event_date IS NULL. This one fixes rows where BOTH dates are set
and differ — a separate defect with a separate cause.

The cause: the Livestock Operations block's Service tab sent only `service_date`
and its Diagnosis tab only `diagnosis_date`, and api/new_livestock_event
then fell through to today() for event_date. A backdated entry therefore stored the
date the user typed in the type-specific field and today's date in event_date. That
fallback is fixed (the `date_key` argument), so this patch is a one-off repair of
what the old behaviour recorded.

The type-specific date wins, because it is the one the form actually collected from
the user — event_date was never entered, it was defaulted. event_date is the
canonical date every guard in livestock_guards.py reads, so leaving the two out of
step means the age and interval rules evaluate against a date the event did not
happen on.

Deliberately NOT touched: the three Calving rows with a NULL event_date and no
type-specific date to recover it from. There is no non-guessed source for those, so
they are left for a human. See the ledger.
"""

import frappe

from upande_livestock.serverscripts.common.events import new_livestock_event

# event_type -> the field that carries the date the user actually entered.
TYPE_DATE_FIELD = {
	"Service": "service_date",
	"Pregnancy Diagnosis": "diagnosis_date",
}


def execute():
	if not frappe.db.table_exists("Livestock Event"):
		return

	total = 0
	for event_type, date_field in TYPE_DATE_FIELD.items():
		rows = frappe.db.sql(
			f"""SELECT name, `{date_field}` AS type_date, event_date
			    FROM `tabLivestock Event`
			    WHERE event_type = %s
			      AND `{date_field}` IS NOT NULL
			      AND event_date IS NOT NULL
			      AND `{date_field}` <> event_date""",
			(event_type,),
			as_dict=True,
		)
		for row in rows:
			frappe.db.set_value(
				"Livestock Event",
				row.name,
				"event_date",
				row.type_date,
				update_modified=False,
			)
		if rows:
			print(f"  {event_type}: aligned {len(rows)} row(s) to {date_field}")
		total += len(rows)

	frappe.db.commit()
	print(f"Aligned event_date with the type-specific date on {total} Livestock Event row(s).")
