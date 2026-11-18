# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which ways of feeding are switched on, on the desk and on the phone.

Three modes: the System run (from the recipe), Manual configuration (the
operator writes the recipe) and the Day sheet (plan against actual, with
Amend). Each has a "show on desk" and a "show on phone" tick in Livestock
Settings. The server refuses a mode that is off on BOTH, so a hidden tab cannot
be reached by calling the endpoint directly; a mode on for only one side still
works, since the desk and the phone share these endpoints.

A site that never stored a tick reads the defaults: System and Day sheet on,
Manual configuration off.
"""

import frappe
from frappe import _
from frappe.utils import cint

from upande_livestock.serverscripts.common.timings import read_setting

SYSTEM = "system"
MANUAL = "manual"
DAY_SHEET = "day_sheet"

# mode -> (label in the sentence, default for desk, default for phone)
MODES = {
	SYSTEM: ("System feeding", 1, 1),
	MANUAL: ("Manual configuration feeding", 0, 0),
	DAY_SHEET: ("The feeding day sheet", 1, 1),
}


def field(mode, where):
	return f"feed_{mode}_{where}"


def is_on(mode, where):
	"""Whether `mode` is shown on `where` ("desk" or "phone")."""
	default = MODES[mode][1 if where == "desk" else 2]
	value = read_setting(field(mode, where))
	return bool(default) if value in (None, "") else bool(cint(value))


def flags():
	"""`{mode: {desk: bool, phone: bool}}` for every mode."""
	return {m: {"desk": is_on(m, "desk"), "phone": is_on(m, "phone")} for m in MODES}


def assert_on(mode):
	"""Refuse in plain words when `mode` is off on both the desk and the phone."""
	if is_on(mode, "desk") or is_on(mode, "phone"):
		return
	frappe.throw(
		_(
			"{0} is turned off. Turn it on in Livestock Settings, under Feeding, Feed types."
		).format(_(MODES[mode][0]))
	)
