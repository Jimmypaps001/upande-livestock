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
against itself — a field that did not exist on the doctype, so in the browser it
always compared undefined to undefined and was, in practice, a plain interval
check with no real vaccine-identity comparison behind it. That is why
INTERVAL_RULES has no Vaccination entry below: ported as written, it would
reject same-visit multi-vaccine recording on real data (see the comment above
INTERVAL_RULES).

That blocker has since been lifted — Livestock Event now carries a `drug_issues`
child table whose rows name an actual `item_code`, so "the same vaccine again too
soon" is finally expressible. The rule is still not implemented here, because no
historical row has drug_issues data to compare against and the check would only
bind on newly recorded events; it is a deliberate to-do, not an oversight.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate

from upande_livestock.serverscripts.common.timings import TIMING_DEFAULTS, read_setting

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


# event_type -> a min/max age window, both ends inclusive. Distinct from
# AGE_RULES, which only has a floor.
AGE_WINDOW_RULES = {
	"Dehorning": {
		"min_setting": "min_dehorning_age_months",
		"min_default": TIMING_DEFAULTS["min_dehorning_age_months"],
		"max_setting": "max_dehorning_age_months",
		"max_default": TIMING_DEFAULTS["max_dehorning_age_months"],
		"label": "dehorning",
	},
}

# Event types that can only genuinely happen once for an animal on a given day.
#
# The list is deliberately short. Excluded on purpose:
#   * Birth — record_calf_births() creates one Birth event PER CALF for the same
#     dam on the same day. Guarding it would break multiple-birth recording, which
#     is the whole point of that flow.
#   * Vaccination / Deworming — several different drugs in one visit is normal.
#   * Check Up / Health Case — these are created from a reference document, and an
#     animal can legitimately be seen twice in a day.
#   * Service — double insemination within one day is a real practice.
#   * Milking / Feeding — herd-level, not per-animal.
DUPLICATE_ONCE_PER_DAY = {
	"Calving": "custom_related_pregnancy",
	"Abortion": "custom_related_pregnancy",
	"Drying Off": None,
	"Pregnancy Diagnosis": None,
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
	#
	# NULLIF(..., '') on both sides, not a bare IS NOT NULL: a Link field
	# cleared through some UI or import path can land as '' rather than NULL,
	# and '' IS NOT NULL is true in SQL. Without this, two genuinely unrelated
	# Calving rows that both happened to hold '' would satisfy
	# `field = shared_value` ('' = '') and be silently exempted from the
	# interval check — the same failure class this exemption exists to avoid.
	# read_setting()/_setting() already treat `value in (None, "")` as unset;
	# this clause is the same rule, just expressed in SQL.
	exempt_clause = ""
	exempt_field = rule.get("exempt_when_shared")
	if exempt_field:
		exempt_clause = f"""AND NOT (
			NULLIF(%(shared_value)s, '') IS NOT NULL
			AND NULLIF(`{exempt_field}`, '') IS NOT NULL
			AND NULLIF(`{exempt_field}`, '') = NULLIF(%(shared_value)s, '')
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


def _check_age_window(doc):
	"""Reject an event whose animal is outside the type's permitted age window.

	Dehorning is the only such rule today. It existed for months as a browser-only
	check in public/js/livestock_event.js, which every non-desk path — REST, the
	Operations block, data import, the mobile client — walked straight past.

	A 0 on either end disables that end, matching how _setting treats the floor
	rules. An animal with no date of birth is never blocked, as in _check_age.
	"""
	rule = AGE_WINDOW_RULES.get(doc.event_type)
	if not rule or not doc.event_date:
		return

	low = _setting(rule["min_setting"], rule["min_default"])
	high = _setting(rule["max_setting"], rule["max_default"])
	age = animal_age_months(doc.animal, doc.event_date)
	if age is None:
		return

	if low and age < low:
		frappe.throw(
			_(
				"This animal is {0} months old — too young for {1}, which starts at {2} months. "
				"Change Livestock Settings → {3} if that is wrong."
			).format(int(age), rule["label"], low, frappe.unscrub(rule["min_setting"]))
		)
	if high and age > high:
		frappe.throw(
			_(
				"This animal is {0} months old — past the {1} window, which ends at {2} months. "
				"Change Livestock Settings → {3} if that is wrong."
			).format(int(age), rule["label"], high, frappe.unscrub(rule["max_setting"]))
		)


def _check_duplicate(doc):
	"""Reject a second event of a once-per-day type for the same animal and date.

	Motivated by real data: CALVING-2026-00002 and CALVING-2026-00003 are both
	Calvings for SHAWN-129539, created 61 minutes apart. Neither has an event_date,
	which is why this guard would not have caught them at the time — event_date is
	mandatory for new events now, so the recurrence is what this closes.

	Where a type names an exemption field, two rows sharing a non-null value in it
	are one event split across records (a multiple birth), not a duplicate — the
	same rule, and the same NULLIF('') care, as _check_interval's
	`exempt_when_shared`.
	"""
	if doc.event_type not in DUPLICATE_ONCE_PER_DAY or not doc.event_date:
		return

	params = {
		"animal": doc.animal,
		"event_type": doc.event_type,
		"event_date": doc.event_date,
		"name": doc.name or "new",
	}
	exempt_clause = ""
	exempt_field = DUPLICATE_ONCE_PER_DAY[doc.event_type]
	if exempt_field:
		exempt_clause = f"""AND NOT (
			NULLIF(%(shared_value)s, '') IS NOT NULL
			AND NULLIF(`{exempt_field}`, '') IS NOT NULL
			AND NULLIF(`{exempt_field}`, '') = NULLIF(%(shared_value)s, '')
		)"""
		params["shared_value"] = doc.get(exempt_field)

	existing = frappe.db.sql(
		f"""SELECT name FROM `tabLivestock Event`
		    WHERE animal = %(animal)s
		      AND event_type = %(event_type)s
		      AND event_date = %(event_date)s
		      AND docstatus = 1
		      AND name != %(name)s
		      {exempt_clause}
		    LIMIT 1""",
		params,
		as_dict=True,
	)
	if not existing:
		return

	frappe.throw(
		_(
			"{0} already has a submitted {1} on {2} ({3}). Cancel or amend that one "
			"instead of recording a second."
		).format(
			doc.animal,
			doc.event_type,
			frappe.utils.formatdate(doc.event_date),
			existing[0].name,
		),
		frappe.DuplicateEntryError,
	)


def check_guards(doc):
	"""Run every guard that applies to this event's type."""
	if not doc.event_type or not doc.animal:
		return
	_check_age(doc)
	_check_age_window(doc)
	_check_interval(doc)
	_check_duplicate(doc)
