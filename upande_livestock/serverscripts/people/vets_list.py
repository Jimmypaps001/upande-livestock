# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Vets as people: each vet's KPIs over a period, for the Vets screen and the phone.

One row per Livestock Vet. The counting that the Vet Performance report already
does (cases, check-ups, treatments, outcomes, days to close, drug cost) is that
report's `data()`, reused rather than written twice so the screen and the report
cannot disagree. This adds what the report does not carry: inseminations, pregnancy
diagnoses, the pregnancy rate, last activity, and who the vet is (photo, phone).

HOW A SERVICE IS ATTRIBUTED. A Service event has no `vet` (the field shows only on
the vet event types), it has an `operator`, an Employee. An INTERNAL vet's
inseminations are the services whose operator is their Employee; an EXTERNAL vet
has no Employee, so none are attributed and the figure reads 0 rather than a guess.

PREGNANCY RATE = services (by that vet, in the period) whose pregnancy was later
confirmed / services. Services still awaiting their diagnosis count in the
denominator: the rate is "so far", and says how many are still pending.

Payload (all optional): {"period": "30d"|"90d"|"month"|"year"|"12m", "from": date,
"to": date, "include_disabled": 0|1}. An explicit from/to wins over `period`.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.upande_livestock.report.vet_performance.vet_performance import data as report_data

DEFAULT_PERIOD = "90d"
PERIODS = ("30d", "90d", "month", "year", "12m")


def period_window(period=None, start=None, end=None, on=None):
	"""(start, end) dates for a named period, or for explicit dates.

	Pure but for `today()`; `on` pins the day for tests.
	"""
	on = getdate(on or today())
	if start or end:
		s, e = getdate(start or add_days(on, -90)), getdate(end or on)
	elif period == "30d":
		s, e = add_days(on, -29), on
	elif period == "month":
		s, e = on.replace(day=1), on
	elif period == "year":
		s, e = on.replace(month=1, day=1), on
	elif period == "12m":
		s, e = add_days(add_months(on, -12), 1), on
	else:  # "90d" and anything unrecognised
		s, e = add_days(on, -89), on
	if s > e:
		s, e = e, s
	return s, e


def pregnancy_rate(services, confirmed):
	"""Percent of services confirmed in calf, one decimal; None with no services."""
	if not services:
		return None
	return round(100.0 * confirmed / services, 1)


def initials(name):
	parts = [p for p in (name or "").replace(".", " ").split() if p and p.lower() not in ("dr", "dr.")]
	if not parts:
		return "?"
	return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def _service_figures(vets, start, end):
	"""{vet: {services, confirmed, pending}} for services by each internal vet's Employee."""
	by_employee = {v.employee: v.name for v in vets if v.employee}
	out = {v.name: {"services": 0, "confirmed": 0, "pending": 0, "last": None} for v in vets}
	if not by_employee:
		return out
	for s in frappe.get_all(
		"Livestock Event",
		filters={
			"docstatus": 1, "event_type": "Service", "operator": ["in", list(by_employee)],
			"event_date": ["between", [start, end]],
		},
		fields=["operator", "event_date", "pregnancy_confirmation_status"], limit=1000000,
	):
		row = out[by_employee[s.operator]]
		row["services"] += 1
		if s.pregnancy_confirmation_status == "Confirmed":
			row["confirmed"] += 1
		elif s.pregnancy_confirmation_status in (None, "", "Pending"):
			row["pending"] += 1
		row["last"] = max(filter(None, [row["last"], s.event_date]))
	return out


def _pd_figures(names, start, end):
	"""{vet: {pds, last}}: Pregnancy Diagnosis events recorded under each vet."""
	out = {n: {"pds": 0, "last": None} for n in names}
	for e in frappe.get_all(
		"Livestock Event",
		filters={
			"docstatus": 1, "event_type": "Pregnancy Diagnosis", "vet": ["in", names],
			"event_date": ["between", [start, end]],
		},
		fields=["vet", "event_date"], limit=1000000,
	):
		row = out[e.vet]
		row["pds"] += 1
		row["last"] = max(filter(None, [row["last"], e.event_date]))
	return out


def _last_activity(vets):
	"""Latest dated record of any kind a vet is named on, over all time (or None)."""
	names = [v.name for v in vets]
	last = {n: None for n in names}

	def bump(vet, d):
		if vet in last and d:
			last[vet] = max(filter(None, [last[vet], getdate(d)]))

	for table, vet_field, date_field in (
		("Livestock Health Case", "vet", "opened_date"),
		("Livestock Diagnosis", "vet", "diagnosis_date"),
		("Livestock Event", "vet", "event_date"),
	):
		for r in frappe.db.sql(
			f"SELECT `{vet_field}` AS vet, MAX(`{date_field}`) AS d FROM `tab{table}` "
			f"WHERE docstatus = 1 AND `{vet_field}` IN %(v)s GROUP BY `{vet_field}`",
			{"v": names}, as_dict=True,
		):
			bump(r.vet, r.d)
	by_employee = {v.employee: v.name for v in vets if v.employee}
	if by_employee:
		for r in frappe.db.sql(
			"SELECT operator, MAX(event_date) AS d FROM `tabLivestock Event` "
			"WHERE docstatus = 1 AND event_type = 'Service' AND operator IN %(e)s GROUP BY operator",
			{"e": list(by_employee)}, as_dict=True,
		):
			bump(by_employee[r.operator], r.d)
	return last


def build_rows(start, end, include_disabled=False):
	filters = {} if include_disabled else {"enabled": 1}
	vets = frappe.get_all(
		"Livestock Vet", filters=filters,
		fields=["name", "vet_name", "vet_type", "enabled", "employee", "phone", "email", "user",
		        "registration_number", "qualification", "licence_expiry", "practice_name", "supplier"],
		order_by="vet_name asc", limit=1000,
	)
	if not vets:
		return []
	kpis = {r["vet"]: r for r in report_data(frappe._dict(), start, end)}
	services = _service_figures(vets, start, end)
	pds = _pd_figures([v.name for v in vets], start, end)
	last = _last_activity(vets)
	images = {}
	emps = [v.employee for v in vets if v.employee]
	if emps:
		images = dict(frappe.get_all("Employee", filters={"name": ["in", emps]},
		                             fields=["name", "image"], as_list=True))

	today_ = getdate(today())
	rows = []
	for v in vets:
		k = kpis.get(v.name, {})
		s = services[v.name]
		closed = sum(k.get(x, 0) for x in ("recovered", "chronic", "died", "culled"))
		expired = bool(v.licence_expiry and getdate(v.licence_expiry) < today_)
		rows.append({
			"value": v.name,
			"label": v.vet_name or v.name,
			"vet": v.name,
			"vet_name": v.vet_name or v.name,
			"type": v.vet_type,
			"enabled": int(v.enabled or 0),
			"initials": initials(v.vet_name),
			"image": images.get(v.employee) or "",
			"phone": v.phone or "",
			"email": v.email or "",
			"employee": v.employee or "",
			"supplier": v.supplier or "",
			"practice_name": v.practice_name or "",
			"registration_number": v.registration_number or "",
			"qualification": v.qualification or "",
			"licence_expiry": str(v.licence_expiry) if v.licence_expiry else None,
			"licence_expired": expired,
			"kpis": {
				"cases_opened": k.get("cases_opened", 0),
				"cases_closed": closed,
				"cases_open_now": k.get("still_open", 0),
				"treatments": k.get("treatments", 0),
				"check_ups": k.get("check_ups", 0),
				"inseminations": s["services"],
				"pds_done": pds[v.name]["pds"],
				"services_confirmed": s["confirmed"],
				"services_pending": s["pending"],
				"pregnancy_rate": pregnancy_rate(s["services"], s["confirmed"]),
				"avg_days_to_close": k.get("avg_days_to_close") or None,
				"drug_cost": flt(k.get("drug_cost", 0), 2),
				"last_activity": str(last[v.name]) if last.get(v.name) else None,
			},
		})
	return rows


@frappe.whitelist()
def vets_list(period=None, payload=None, **kw):
	"""Every vet with their KPIs for the period. See the module docstring."""

	def go():
		guard_read("Livestock Vet")
		d = as_dict(payload) if payload else {}
		# `period` may arrive as its own argument (a phone's GET) or inside payload.
		p = period if isinstance(period, str) and period.strip() and not period.strip().startswith("{") else d.get("period")
		if isinstance(period, str) and period.strip().startswith("{"):
			d = {**as_dict(period), **d}
			p = d.get("period")
		start, end = period_window(p or DEFAULT_PERIOD, d.get("from"), d.get("to"))
		return {
			"ok": True,
			"period": p if p in PERIODS else (None if (d.get("from") or d.get("to")) else DEFAULT_PERIOD),
			"from": str(start),
			"to": str(end),
			"vets": build_rows(start, end, bool(int(d.get("include_disabled") or 0))),
		}

	return run(go, "livestock vets_list failed")
