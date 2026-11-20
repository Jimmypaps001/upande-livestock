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


@frappe.whitelist()
def quality_test_options(date=None):
	"""What the form needs: defaults, choices, the farm's limits, and that
	day's milk recordings to link the batch to."""

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
			"recordings": recordings,
			"can_write": bool(frappe.has_permission(DT, "create")),
		}

	return run(go, "livestock quality_test_options failed")


@frappe.whitelist()
def record_quality_test(payload):
	"""Create a Milk Quality Test. `client_ref` makes it safe to send twice: a
	phone that never saw the reply and retries gets the first record back."""

	def go():
		guard(DT)
		d = as_dict(payload)
		ref = (d.get("client_ref") or "").strip()[:140]
		if ref:
			existing = frappe.db.get_value(DT, {"client_ref": ref}, "name")
			if existing:
				return _full(existing, duplicate=True)

		values = mq.clean(d)
		doc = frappe.new_doc(DT)
		doc.sample_date = mq.check_date(d.get("sample_date"))
		doc.shift = values.pop("shift") or ""
		doc.sample_type = values.pop("sample_type") or "Bottle sample"
		for k, v in values.items():
			doc.set(k, v)
		doc.buyer = (d.get("buyer") or "").strip() or None
		if doc.buyer and not frappe.db.exists("Customer", doc.buyer):
			frappe.throw(_("{0} is not a customer.").format(doc.buyer))
		doc.milk_recording = (d.get("milk_recording") or "").strip() or None
		doc.sensory_note = (d.get("sensory_note") or "").strip()[:140]
		doc.remarks = (d.get("remarks") or "").strip()
		doc.lab_slip = (d.get("lab_slip") or "").strip() or None
		doc.client_ref = ref or None
		doc.insert()
		return _full(doc.name)

	return run(go, "livestock record_quality_test failed")


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


@frappe.whitelist()
def quality_test(name):
	def go():
		guard_read(DT)
		if not frappe.db.exists(DT, name):
			frappe.throw(_("{0} is not a milk quality test.").format(name))
		return _full(name)

	return run(go, "livestock quality_test failed")
