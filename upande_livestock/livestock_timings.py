# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Breeding, husbandry, age and interval timing parameters, read from Livestock
Settings.

Every default here equals the value that was previously hardcoded — either in
the Livestock Event controller (the first eleven) or in public/js/animal_event.js
(the rest, consumed by upande_livestock.livestock_guards) — so an unconfigured
site behaves exactly as before.

A setting of 0 is honoured, not treated as unset — that is how
post_calving_min_service_days and post_abortion_min_service_days are disabled.
See livestock_settings.py for the zero-rejection rule that applies to every
other TIMING_DEFAULTS field, including all nine age/interval fields: unlike
the two disable-capable pair, none of "0 months minimum age" or "0 days
minimum interval" is ever a real configuration.

These 20 fields deliberately live in one dict rather than several that could
drift apart: every Int consumer — the seeder below (via ALL_TIMING_DEFAULTS),
the zero-rejection validation in livestock_settings.py, get_timing(), and
livestock_guards.AGE_RULES/INTERVAL_RULES — reads its defaults from here, so
adding or changing an Int field happens exactly once.

default_calf_herd_min_age and default_calf_herd_max_age are NOT in
TIMING_DEFAULTS, on purpose: they are Float fields (fractional months are
meaningful — "2.5 months"), and get_timing() unconditionally cint()s its
result, which would silently truncate them. default_calf_herd_min_age's real
default is also 0, and ZERO_IS_INVALID derives its members from TIMING_DEFAULTS
minus the two disable-capable fields — including a Float 0 default in
TIMING_DEFAULTS would make it wrongly rejected as "cannot be 0" the first time
anyone saves the real default back unchanged. They live in the separate
FLOAT_TIMING_DEFAULTS dict below instead, which only the seeder consumes (via
read_setting/frappe.db.set_single_value, both type-agnostic) — never
get_timing() or ZERO_IS_INVALID.

ALL_TIMING_DEFAULTS merges both and is the one thing that must stay in sync
with every Int/Float field on the Livestock Settings DocType — see
test_every_int_or_float_field_is_covered_by_the_seeding_structure in
test_livestock_timings.py, which walks the doctype meta against this dict
rather than a hand-maintained field list, so a future field silently escaping
both dicts (as these four once did) fails loudly instead of shipping unseeded.
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
	# Dehorning age window (currently enforced client-side only, in
	# public/js/livestock_event.js — no server-side guard exists yet; adding
	# one is a separate decision, tracked as a follow-up, not part of this
	# fix). Int-shaped and zero-invalid exactly like the seven above, so they
	# belong in this dict for the same reason.
	"min_dehorning_age_months": 1,
	"max_dehorning_age_months": 6,
	# Herd-movement thresholds. Every one is a day count on which 0 means
	# nothing real — a bull culled 0 days after birth, a cow flagged open the
	# day she calves — so they belong here rather than in the disable-capable
	# set, and the values match the DocType's own defaults so a seeded site and
	# a fresh install agree.
	"bull_cull_max_days": 14,
	"incalf_general_days": 180,
	"heifer_dry_off_before_calving_days": 90,
	"high_yield_days_from_conception": 120,
	"low_yield_days": 60,
	"steamer_days_from_heifers": 90,
	"steamer_days_from_lactation": 60,
	"max_open_days": 200,
}

# Float counterparts of TIMING_DEFAULTS: seeded the same way (see
# ensure_livestock_timing_defaults), but deliberately excluded from
# TIMING_DEFAULTS itself — see the module docstring for why forcing them
# through get_timing()/ZERO_IS_INVALID would be wrong.
FLOAT_TIMING_DEFAULTS = {
	"default_calf_herd_min_age": 0.0,
	"default_calf_herd_max_age": 2.0,
}

# The single structure the seeder (and its enforcing test) walk. Not consumed
# by get_timing() or ZERO_IS_INVALID — both stay scoped to TIMING_DEFAULTS.
ALL_TIMING_DEFAULTS = {**TIMING_DEFAULTS, **FLOAT_TIMING_DEFAULTS}


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
