# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Breeding, husbandry, age and interval timing parameters, read from Livestock
Settings.

Every default here equals the value that was previously hardcoded — either in
the Livestock Event controller (the first eleven) or in public/js/animal_event.js
(the last seven, consumed by upande_livestock.livestock_guards) — so an
unconfigured site behaves exactly as before.

A setting of 0 is honoured, not treated as unset — that is how
post_calving_min_service_days and post_abortion_min_service_days are disabled.
See livestock_settings.py for the zero-rejection rule that applies to every
other timing, including all seven age/interval fields: unlike the two
disable-capable pair, none of "0 months minimum age" or "0 days minimum
interval" is ever a real configuration.

These 18 fields deliberately live in one dict rather than two (one for
breeding/husbandry timings, one for age/interval guard thresholds) that could
drift apart: every consumer — the seeder below, the zero-rejection validation
in livestock_settings.py, and livestock_guards.AGE_RULES/INTERVAL_RULES —
reads its defaults from here, so adding or changing a field happens exactly
once.
"""

import frappe
from frappe.utils import cint

TIMING_DEFAULTS = {
	"post_calving_min_service_days": 45,
	"post_calving_optimal_service_days": 60,
	"post_abortion_min_service_days": 30,
	"gestation_period_days": 280,
	"pregnancy_check_days_after_service": 35,
	"heat_cycle_days": 21,
	"diagnosis_earliest_days": 21,
	"diagnosis_latest_days": 70,
	"gestation_short_warning_days": 260,
	"gestation_long_warning_days": 300,
	"calving_alert_lead_days": 7,
	# Age/interval guard thresholds (upande_livestock.livestock_guards). These
	# seven predate Task 5 and were, until now, excluded from this dict — which
	# meant they got none of the protection below: an unset field silently
	# read back as 0 (see ensure_livestock_timing_defaults) once anything
	# saved Livestock Settings, disabling every age/interval guard.
	"min_service_age_months": 15,
	"min_calving_age_months": 24,
	"min_calving_interval_days": 270,
	"min_vaccination_interval_days": 21,
	"min_deworming_interval_days": 90,
	"min_hoof_trimming_interval_days": 90,
	"min_weight_recording_interval_days": 7,
}


def read_setting(fieldname):
	"""The raw stored value of a Livestock Settings field, or None if never set.

	Deliberately NOT `frappe.db.get_single_value()`: that helper casts its
	result by fieldtype, so an unset Int field comes back as `cint(None)` == 0
	— indistinguishable from a deliberately configured zero, which would make
	every default in this module unreachable and would make `0` un-honourable.

	Shared with `upande_livestock.install.ensure_livestock_timing_defaults`,
	which needs the same "is this row really absent" answer to decide what to
	seed without ever overwriting a farm's configured value.
	"""
	rows = frappe.db.sql(
		"select `value` from `tabSingles` where doctype=%s and field=%s",
		("Livestock Settings", fieldname),
	)
	return rows[0][0] if rows else None


def get_timing(key):
	"""The configured value for `key`, or its documented default.

	Raises KeyError on an unknown key, so a typo fails loudly rather than
	silently behaving as 0.
	"""
	default = TIMING_DEFAULTS[key]
	value = read_setting(key)
	if value in (None, ""):
		return default
	return cint(value)
