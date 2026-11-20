# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""quality_test_options: split out of quality.quality_tests; that module still re-exports it, so the old dotted path resolves."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common import milk_quality_test as mq
from upande_livestock.serverscripts.common import quality


@frappe.whitelist()
def quality_test_options(date=None):
	"""What the form needs: defaults, choices, the farm's limits, and that
	day's milk recordings to link the batch to."""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.quality.quality_tests import DT


	def go():
		guard_read(DT)
		on = mq.check_date(date)
		lim = mq.limits()
		buyer = frappe.db.get_value("Customer", {"name": ["like", "%Westwood%"]}, "name")
		recordings = frappe.get_all(
			"Milk Recording",
			filters={"docstatus": 1, "recording_date": on},
			fields=["name", "herd", "milking_time", "net_yield_kg"],
			order_by="milking_time",
			limit=50,
		)
		for r in recordings:
			r["milking_time"] = str(r.get("milking_time") or "")[:5]
		return {
			"ok": True,
			"date": on,
			"default_buyer": buyer or "",
			"sample_types": list(mq.SAMPLE_TYPES),
			"shifts": list(mq.SHIFTS),
			"limits": lim,
			"scc_ceiling": quality.scc_ceiling(),
			"recordings": recordings,
			"can_write": bool(frappe.has_permission(DT, "create")),
		}

	return run(go, "livestock quality_test_options failed")
