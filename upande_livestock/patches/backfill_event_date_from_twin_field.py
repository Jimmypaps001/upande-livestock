# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Backfill event_date on Service / Pregnancy Diagnosis events from their own
dedicated date field.

LivestockEvent.validate() now has a CONDITIONAL MANDATORY: EVENT DATE check
(added alongside this patch) requiring event_date on every NEW Livestock
Event. That check closes a gap where three duplicate Client-Script-era
`frappe.ui.form.on("Livestock Event", ...)` registrations in
public/js/livestock_event.js were silently wiping event_date to null on every
non-Movement desk save (two of them ran `frm.set_value("event_date", null)`
whenever `event_type != "Movement"`). livestock_guards.py's age/interval rules
also return early whenever event_date is falsy, so those events were silently
escaping every guard this project built, not just missing a date on screen.

On kaitet.local, 5 submitted Livestock Event rows have event_date IS NULL:
3 Calving, 1 Pregnancy Diagnosis, 1 Service.

Only 2 of the 5 are recoverable here without guessing:
  - Service and Pregnancy Diagnosis each carry their own dedicated date field
    (service_date / diagnosis_date). The desk form's own toggle_event_fields()
    even relabels the generic event_date field as "Service Date" / "Diagnosis
    Date" for exactly these two types — event_date and the twin field are, by
    the form's own design, meant to hold the same date. Copying the twin
    field's value across is a safe, non-guessed recovery.

Deliberately NOT touched: Calving has no twin field, and `creation` is NOT
used as a proxy — this site has at least one row whose service_date
(2026-01-01) is deliberately backdated a month from its own creation
timestamp (2026-01-26), so "when the row was saved" is demonstrably not "when
the event happened." Inventing a Calving event_date from creation, or any
other guess, would silently misrepresent real farm history. Those 3 Calving
rows are left NULL. This is safe: the new mandatory check in
LivestockEvent.validate() is deliberately scoped to NEW documents only
(self.is_new()), specifically so these pre-existing, already-submitted
records are never blocked from an ordinary future edit, cancel or amend.

Deliberately narrow:
  - Only fills a blank event_date. A value already present is never
    overwritten, even if it disagrees with the twin field.
  - Only touches Service (from service_date) and Pregnancy Diagnosis (from
    diagnosis_date). No other event type has a same-meaning twin field.
  - Skips a row whose twin field is itself NULL — nothing to copy.

Idempotent: a row already filled no longer matches the WHERE clause, so a
second run touches nothing.
"""

import frappe

# event_type -> the field that duplicates event_date's meaning for that type.
TWIN_FIELD = {
	"Service": "service_date",
	"Pregnancy Diagnosis": "diagnosis_date",
}


def execute():
	if not frappe.db.table_exists("Livestock Event"):
		return

	filled = 0
	for event_type, twin_field in TWIN_FIELD.items():
		rows = frappe.db.sql(
			f"""SELECT name, `{twin_field}` AS twin_value
			    FROM `tabLivestock Event`
			    WHERE event_type = %s
			      AND event_date IS NULL
			      AND `{twin_field}` IS NOT NULL""",
			(event_type,),
			as_dict=True,
		)
		for row in rows:
			frappe.db.set_value(
				"Livestock Event", row.name, "event_date", row.twin_value, update_modified=False
			)
			filled += 1

	frappe.db.commit()
	print(f"Backfilled event_date on {filled} Livestock Event rows from their twin date field")
