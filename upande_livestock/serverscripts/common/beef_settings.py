# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Beef herd section of Livestock Settings, read with its defaults.

The Int fields are timings (common/timings.py); these are the two that are not
numbers. Read raw from tabSingles for the reason `read_setting` gives: a Check
with no row casts to 0, which would silently turn the inbreeding warning off on
a site nobody has saved Settings on.
"""

from upande_livestock.serverscripts.common.timings import read_setting

#: Seeded alongside the timings by install.ensure_livestock_timing_defaults.
BEEF_DEFAULTS = {"default_service_type": "Natural", "kinship_check": 1}


def default_service_type():
	value = read_setting("default_service_type")
	return value if value in ("Natural", "A.I.") else BEEF_DEFAULTS["default_service_type"]


def kinship_check_on():
	value = read_setting("kinship_check")
	if value in (None, ""):
		return bool(BEEF_DEFAULTS["kinship_check"])
	return value not in ("0", 0)
