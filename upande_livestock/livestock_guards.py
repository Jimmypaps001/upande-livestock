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
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate

from upande_livestock.livestock_timings import read_setting

# event_type -> the Livestock Settings field and the client script's old default
AGE_RULES = {
	"Service": {"setting": "min_service_age_months", "default": 15, "label": "service"},
	"Calving": {"setting": "min_calving_age_months", "default": 24, "label": "calving"},
}

# event_type -> minimum days since the last event of the same kind
INTERVAL_RULES = {
	"Calving": {
		"setting": "min_calving_interval_days",
		"default": 270,
		"against": ("Calving",),
		"label": "calving",
	},
	"Vaccination": {
		"setting": "min_vaccination_interval_days",
		"default": 21,
		"against": ("Vaccination",),
		"label": "vaccination",
	},
	"Deworming": {
		"setting": "min_deworming_interval_days",
		"default": 90,
		"against": ("Deworming",),
		"label": "deworming",
	},
	"Hoof Trimming": {
		"setting": "min_hoof_trimming_interval_days",
		"default": 90,
		"against": ("Hoof Trimming",),
		"label": "hoof trimming",
	},
	"Weight Recording": {
		"setting": "min_weight_recording_interval_days",
		"default": 7,
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
	if not minimum:
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

	previous = frappe.db.sql(
		"""SELECT name, event_date FROM `tabLivestock Event`
		   WHERE animal = %(animal)s
		     AND event_type IN %(types)s
		     AND docstatus = 1
		     AND name != %(name)s
		     AND event_date <= %(event_date)s
		   ORDER BY event_date DESC LIMIT 1""",
		{
			"animal": doc.animal,
			"types": rule["against"],
			"name": doc.name or "new",
			"event_date": doc.event_date,
		},
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
