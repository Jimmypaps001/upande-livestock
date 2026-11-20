# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A buyer's quality result for a batch of milk: record it, list it, open it.

The desk Quality page and the phone call these same four functions.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, today

from upande_livestock.serverscripts.common import milk_quality_test as mq
from upande_livestock.serverscripts.common.envelope import as_dict, guard, guard_read, run

DT = mq.DOCTYPE

LIST_FIELDS = [
	"name", "sample_date", "shift", "sample_type", "buyer", "milk_recording", "quantity_l",
	"receiving_temp_c", "ph", "tta", "snf_percent", "freezing_point", "specific_gravity",
	"protein_percent", "butterfat_percent", "resazurin_score", "resazurin_result",
	"antibiotics", "hydrogen_peroxide", "frothing", "aflatoxin_ppt", "sensory_score",
	"sensory_note", "overall_result", "failed_tests", "aflatoxin_over_limit", "remarks",
	"lab_slip", "recorded_by", "creation",
]


def _row(r, lim):
	"""A list row with the per-parameter pass/fail chips the pages draw."""
	r = dict(r)
	for k in ("sample_date", "creation"):
		r[k] = str(r.get(k) or "")
	for k in mq.NUMERIC_FIELDS + ("quantity_l",):
		r[k] = r.get(k) if r.get(k) else None  # 0 is "not recorded" on a Float column
	r["aflatoxin_over_limit"] = bool(r.get("aflatoxin_over_limit"))
	r["checks"] = mq.checks(r, lim)
	return r


def _full(name, duplicate=False):
	row = frappe.db.get_value(DT, name, LIST_FIELDS, as_dict=True)
	out = {"ok": True, "name": name, "duplicate": duplicate, "test": _row(row, mq.limits())}
	out["overall_result"] = out["test"]["overall_result"]
	out["failed_tests"] = out["test"]["failed_tests"]
	return out


@frappe.whitelist()
def quality_tests(filters=None, limit=50, start=0):
	"""History, newest first. Filters: from_date, to_date, buyer, sample_type,
	overall_result. Defaults to the last 90 days."""

	def go():
		guard_read(DT)
		f = as_dict(filters)
		cond = {}
		frm = f.get("from_date") or add_days(today(), -90)
		to = f.get("to_date") or today()
		cond["sample_date"] = ["between", [frm, to]]
		for k in ("buyer", "sample_type", "overall_result"):
			if f.get(k):
				cond[k] = f[k]
		n = max(1, min(cint(limit) or 50, 500))
		lim = mq.limits()
		rows = frappe.get_all(
			DT, filters=cond, fields=LIST_FIELDS,
			order_by="sample_date desc, creation desc",
			start=cint(start), limit=n,
		)
		total = frappe.db.count(DT, cond)
		return {
			"ok": True,
			"tests": [_row(r, lim) for r in rows],
			"total": total,
			"limits": lim,
			"can_write": bool(frappe.has_permission(DT, "create")),
		}

	return run(go, "livestock quality_tests failed")


# The endpoints split out into their own modules. Imported here so the dotted paths the phone and
# the desk already call still resolve (Frappe checks the whitelist by function identity).
# Last, because each of them imports helpers from this module.
from upande_livestock.serverscripts.quality.quality_test_options import quality_test_options  # noqa: E402,F401
from upande_livestock.serverscripts.quality.record_quality_test import record_quality_test  # noqa: E402,F401
from upande_livestock.serverscripts.quality.quality_test import quality_test  # noqa: E402,F401
