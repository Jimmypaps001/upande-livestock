# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Repair the seven age/interval guard settings found stored as a literal '0'.

min_service_age_months, min_calving_age_months, min_calving_interval_days,
min_vaccination_interval_days, min_deworming_interval_days,
min_hoof_trimming_interval_days and min_weight_recording_interval_days predate
Task 5 and, until this task added them to TIMING_DEFAULTS, were covered by
neither ensure_livestock_timing_defaults() nor LivestockSettings' zero-rejection
validation. On kaitet.local every one of them had already been coerced to the
literal string '0' in `tabSingles` by some earlier save of Livestock Settings
(see `frappe.model.base_document.BaseDocument.get_valid_dict`, and
`ensure_livestock_timing_defaults`'s docstring) — silently disabling every
guard in `upande_livestock.livestock_guards`.

ensure_livestock_timing_defaults() cannot fix this on its own: it only ever
fills a field that has *no* row at all, on purpose, so it never overwrites a
farm's real configured value — including a deliberate 0 (that is how
post_calving_min_service_days and post_abortion_min_service_days work). None
of these seven fields can ever validly be 0, though (see ZERO_IS_INVALID in
livestock_settings.py), so a stored '0' here can only be this historical bug,
never a deliberate choice — which is what makes repairing it safe.

Deliberately narrow: touches only rows whose stored value is the exact string
'0', for exactly these seven field names. A field already holding its real
default, an unset field (no row), or any other configured value is left
untouched. Idempotent — running this twice repairs nothing the second time.
"""

import frappe

from upande_livestock.livestock_timings import TIMING_DEFAULTS

FIELDS = (
	"min_service_age_months",
	"min_calving_age_months",
	"min_calving_interval_days",
	"min_vaccination_interval_days",
	"min_deworming_interval_days",
	"min_hoof_trimming_interval_days",
	"min_weight_recording_interval_days",
)


def execute():
	if not frappe.db.table_exists("Singles"):
		return []

	repaired = []
	for fieldname in FIELDS:
		rows = frappe.db.sql(
			"select `value` from `tabSingles` where doctype='Livestock Settings' and field=%s",
			(fieldname,),
		)
		if not rows or rows[0][0] != "0":
			continue

		default = TIMING_DEFAULTS[fieldname]
		frappe.db.sql(
			"""update `tabSingles` set `value`=%s
			   where doctype='Livestock Settings' and field=%s and `value`='0'""",
			(str(default), fieldname),
		)
		repaired.append((fieldname, default))

	frappe.db.commit()
	for fieldname, default in repaired:
		print(f"Repaired {fieldname}: '0' -> {default}")
	return repaired
