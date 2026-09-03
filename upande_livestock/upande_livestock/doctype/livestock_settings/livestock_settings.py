# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from upande_livestock.serverscripts.common.timings import TIMING_DEFAULTS

# 0 is a legitimate configuration for these two: "no waiting period".
ZERO_MEANS_DISABLED = {"post_calving_min_service_days", "post_abortion_min_service_days"}

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


class LivestockSettings(Document):
	def validate(self):
		for fieldname, default in ZERO_IS_INVALID.items():
			value = self.get(fieldname)
			if value in (None, ""):
				continue
			if cint(value) == 0:
				frappe.throw(
					_("{0} cannot be 0 — that is not a valid configuration. The default is {1}.").format(
						frappe.bold(self.meta.get_label(fieldname) or frappe.unscrub(fieldname)), default
					)
				)
