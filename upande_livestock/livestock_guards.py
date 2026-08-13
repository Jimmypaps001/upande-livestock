# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Server-side age and interval guards for Livestock Event.

These rules previously lived only in public/js/animal_event.js, which meant the
REST API, api/operations.record_birth, data import and the mobile client all
bypassed them. The client script keeps its copies for fast feedback; this module
is what actually binds.

Every threshold reads a Livestock Settings field, falling back to the default the
client script used, so no site's behaviour changes on deploy. A configured 0
disables the rule.

The old client-side vaccination rule compared frm.doc.custom_vaccine_drug_name
against itself — a field that does not exist on the doctype, so in the browser
it always compared undefined to undefined and was, in practice, a plain
interval check with no real vaccine-identity comparison behind it. That is why
INTERVAL_RULES has no Vaccination entry below: ported as written, it would
reject same-visit multi-vaccine recording on real data (see the comment above
INTERVAL_RULES). It returns once a real vaccine field exists to compare on.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate

from upande_livestock.livestock_timings import TIMING_DEFAULTS, read_setting

# event_type -> the Livestock Settings field and its default. The default is
# read out of TIMING_DEFAULTS rather than repeated as a literal here: that is
# the one place these seven fields' defaults are declared (shared with the
# seeder and the zero-rejection validation in livestock_settings.py), so this
# table and that one cannot drift apart.
AGE_RULES = {
	"Service": {
		"setting": "min_service_age_months",
		"default": TIMING_DEFAULTS["min_service_age_months"],
		"label": "service",
	},
	"Calving": {
		"setting": "min_calving_age_months",
		"default": TIMING_DEFAULTS["min_calving_age_months"],
		"label": "calving",
	},
}

# event_type -> minimum days since the last event of the same kind.
#
# Vaccination is deliberately absent: on kaitet.local, 383 same-animal
# Vaccination pairs across 12 animals sit under the 21-day default, almost
# all 0 days apart — several different vaccines given in one visit. The rule
# is only meaningful as "the same vaccine again too soon", which needs a field
# recording which vaccine was given; the doctype has none (see the module
# docstring's note on custom_vaccine_drug_name). min_vaccination_interval_days
# stays in Livestock Settings and in TIMING_DEFAULTS — only this guard is
# withheld, until that field exists to make it meaningful.
INTERVAL_RULES = {
	"Calving": {
		"setting": "min_calving_interval_days",
		"default": TIMING_DEFAULTS["min_calving_interval_days"],
		"against": ("Calving",),
		"label": "calving",
		# A multiple birth (twins, triplets, ...) is recorded as several
		# same-day Calving rows that all share custom_related_pregnancy —
		# one calving event split across records, not several calvings too
		# close together. Rows that share a (non-null) value in this field
		# must not be compared against each other. Two Calving rows that
		# both have no pregnancy link do not "share" anything and are still
		# compared — see _check_interval.
		"exempt_when_shared": "custom_related_pregnancy",
	},
	"Deworming": {
		"setting": "min_deworming_interval_days",
		"default": TIMING_DEFAULTS["min_deworming_interval_days"],
		"against": ("Deworming",),
		"label": "deworming",
	},
	"Hoof Trimming": {
		"setting": "min_hoof_trimming_interval_days",
		"default": TIMING_DEFAULTS["min_hoof_trimming_interval_days"],
		"against": ("Hoof Trimming",),
		"label": "hoof trimming",
	},
	"Weight Recording": {
		"setting": "min_weight_recording_interval_days",
		"default": TIMING_DEFAULTS["min_weight_recording_interval_days"],
		"against": ("Weight Recording",),
		"label": "weight recording",
	},
}


def _setting(fieldname, default):
	"""The configured value for `fieldname`, or `default` when it was never set.

	Uses livestock_timings.read_setting rather than frappe.db.get_single_value:
	that helper runs cast_fieldtype on the result, so an unset Int comes back as
	0 — indistinguishable from a deliberately configured 0. Reading it that way
	would silently disable every rule in this module on any site that had never
	saved Livestock Settings.
	"""
	value = read_setting(fieldname)
	if value in (None, ""):
		return default
	return cint(value)


def animal_age_months(animal, on_date):
	"""Age in months on `on_date`, or None when the animal has no date of birth.

	A missing date of birth must not block recording — plenty of purchased animals
	have never had one entered.
	"""
	dob = frappe.db.get_value("Animal", animal, "date_of_birth")
	if not dob:
		return None
	return flt(date_diff(getdate(on_date), getdate(dob))) / 30.4375


def _check_age(doc):
	rule = AGE_RULES.get(doc.event_type)
	if not rule:
		return

	minimum = _setting(rule["setting"], rule["default"])
	if not minimum or not doc.event_date:
		# frappe.utils.getdate(None) silently returns *today*, not "no date" —
		# without this guard, an event with no event_date (real data:
		# CALVING-2026-00001, SERVICE-2026-00001) would be age-checked against
		# today, a value that drifts with the calendar and has nothing to do
		# with when the event actually happened. Mirrors the same guard
		# _check_interval already has for the same reason.
		return

	age = animal_age_months(doc.animal, doc.event_date)
	if age is None or age >= minimum:
		return

	frappe.throw(
		_(
			"This animal is {0} months old. The minimum age for {1} is {2} months. "
			"Change Livestock Settings → {3} if that is wrong."
		).format(int(age), rule["label"], minimum, frappe.unscrub(rule["setting"]))
	)


def _check_interval(doc):
	rule = INTERVAL_RULES.get(doc.event_type)
	if not rule:
		return

	minimum = _setting(rule["setting"], rule["default"])
	if not minimum or not doc.event_date:
		return

	params = {
		"animal": doc.animal,
		"types": rule["against"],
		"name": doc.name or "new",
		"event_date": doc.event_date,
	}

	# Data-driven, not `if doc.event_type == "Calving"`: any rule can declare
	# a field whose shared, non-null value means "this pair is one event
	# split across records" rather than "two events too close together". A
	# doc with no value in that field shares nothing with anything, so it is
	# still compared against every prior row — only a genuine shared,
	# non-null match is exempted.
	exempt_clause = ""
	exempt_field = rule.get("exempt_when_shared")
	if exempt_field:
		exempt_clause = f"""AND NOT (
			%(shared_value)s IS NOT NULL
			AND `{exempt_field}` IS NOT NULL
			AND `{exempt_field}` = %(shared_value)s
		)"""
		params["shared_value"] = doc.get(exempt_field)

	previous = frappe.db.sql(
		f"""SELECT name, event_date FROM `tabLivestock Event`
		   WHERE animal = %(animal)s
		     AND event_type IN %(types)s
		     AND docstatus = 1
		     AND name != %(name)s
		     AND event_date <= %(event_date)s
		     {exempt_clause}
		   ORDER BY event_date DESC LIMIT 1""",
		params,
		as_dict=True,
	)
	if not previous:
		return

	days = date_diff(doc.event_date, previous[0].event_date)
	if days >= minimum:
		return

	frappe.throw(
		_(
			"Last {0} for this animal was {1} ({2} days ago); the minimum interval is "
			"{3} days. Change Livestock Settings → {4} if that is wrong."
		).format(
			rule["label"],
			frappe.utils.formatdate(previous[0].event_date),
			days,
			minimum,
			frappe.unscrub(rule["setting"]),
		)
	)


def check_guards(doc):
	"""Run every guard that applies to this event's type."""
	if not doc.event_type or not doc.animal:
		return
	_check_age(doc)
	_check_interval(doc)
