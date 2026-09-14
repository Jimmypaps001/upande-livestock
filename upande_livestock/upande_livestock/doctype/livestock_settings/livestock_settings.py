# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from upande_livestock.serverscripts.common.timings import TIMING_DEFAULTS

# 0 is a legitimate configuration for these: "no waiting period" for the first
# two, and "do not tell me about it" for the two health-file lines, which are
# about how long the farm will let a file sit rather than about an animal.
ZERO_MEANS_DISABLED = {
	"post_calving_min_service_days",
	"post_abortion_min_service_days",
	"health_case_concern_days",
	"health_case_stale_days",
}

# Every other timing: 0 cannot mean anything real (a 0-day gestation period,
# a 0-day diagnosis window, etc. is not a configuration choice, it is a
# mistake). Derived from TIMING_DEFAULTS minus the disable-capable pair, so a
# future timing key added there is covered automatically rather than
# silently exempted.
ZERO_IS_INVALID = {
	fieldname: default
	for fieldname, default in TIMING_DEFAULTS.items()
	if fieldname not in ZERO_MEANS_DISABLED
}


def reject_invalid_zeros(values: dict, meta=None) -> None:
	"""Throw if any of `values` sets a field where 0 cannot mean anything real.

	Lifted out of `validate` so the Settings page's write endpoint enforces the
	same rule in the same words. That endpoint deliberately does not save the
	whole document — a full save of this Single coerces every *unset* Int to 0
	(see `install.ensure_livestock_timing_defaults`), which is the incident
	`patches.repair_zeroed_age_interval_settings` exists to undo — so it cannot
	get this check for free from `validate`, and a second copy of the rule
	would be a second copy to keep true.

	Only the keys present in `values` are examined, so a partial patch is
	checked on exactly what it changes.
	"""
	meta = meta or frappe.get_meta("Livestock Settings")
	for fieldname, default in ZERO_IS_INVALID.items():
		if fieldname not in values:
			continue
		value = values[fieldname]
		if value in (None, ""):
			continue
		if cint(value) == 0:
			frappe.throw(
				_("{0} cannot be 0 — that is not a valid configuration. The default is {1}.").format(
					frappe.bold(meta.get_label(fieldname) or frappe.unscrub(fieldname)), default
				)
			)


class LivestockSettings(Document):
	def validate(self):
		reject_invalid_zeros({f: self.get(f) for f in ZERO_IS_INVALID}, self.meta)
