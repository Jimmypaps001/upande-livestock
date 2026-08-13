# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Breeding and husbandry timing parameters, read from Livestock Settings.

Every default here equals the value that was previously hardcoded in the
Livestock Event controller, so an unconfigured site behaves exactly as before.

A setting of 0 is honoured, not treated as unset — that is how
post_abortion_min_service_days is disabled. See livestock_settings.py for the
zero-rejection rule that applies to every other timing.
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
