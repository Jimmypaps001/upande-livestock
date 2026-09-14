# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The case register: the farm's files, grouped, over a period."""

import frappe
from frappe.utils import add_days, flt, getdate, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.common.health_case import (
	CLOSED_STATUSES,
	TREATING_STATUSES,
	concern,
	concern_days,
	days_open,
	stale_days,
)

#: How many files one page of the register holds. A farm with four hundred cases
#: cannot be handed all of them, and a list you scroll for a minute is one
#: nobody reads to the bottom of.
PAGE = 200


@frappe.whitelist()
def health_cases(payload=None):
	"""Every file opened, closed or still open in a period, grouped by state.

	A LIST OF FOUR HUNDRED CASES IS NOT A REGISTER. It is a ward round with no
	ward: the six cows currently being treated are somewhere in it, in date
	order, between cases closed in 2024. So the answer is grouped the way a
	hospital groups files — being treated, and shut — and scoped to a period the
	caller chooses, with the two numbers that actually get asked at the top:
	how many were opened in it and how many were closed.

	OPENED IN A PERIOD AND OPEN IN IT ARE DIFFERENT QUESTIONS, and both are
	answered. A file opened in March and still open in June is not among June's
	openings, but she is very much still a cow under treatment — so the open
	group ignores the period and the counts do not.

	`concern` rides on every open file. Which cases are worrying is a farm
	setting (Livestock Settings > Health), not an opinion held here.
	"""

	def go():
		guard_read("Livestock Health Case")
		d = as_dict(payload) if payload else {}
		# Twelve months back is the register a farm actually looks at. It is a
		# default, not a limit — the page can ask for any window.
		start = getdate(d.get("from") or add_days(today(), -365))
		end = getdate(d.get("to") or today())
		if start > end:
			start, end = end, start

		names = _names(d, start, end)
		rows = frappe.get_all(
			"Livestock Health Case",
			filters={"name": ["in", names]} if names else {"name": ["in", ["__none__"]]},
			fields=["name", "animal", "animal_name", "current_herd", "case_status",
			        "opened_date", "closed_date", "presenting_symptoms",
			        "provisional_diagnosis", "confirmed_diagnosis", "severity",
			        "duration_days", "production_loss_kg", "total_treatment_cost",
			        "vet_called", "vet_name"],
			order_by="opened_date desc, creation desc",
			limit_page_length=PAGE,
		)
		last = _last_treatments([r.name for r in rows])
		counts = _counts(rows)

		files = []
		for r in rows:
			case = dict(r)
			case["days_open"] = days_open(case)
			case["treatments"] = last.get(r.name, {}).get("count", 0)
			case["last_treatment_on"] = last.get(r.name, {}).get("on")
			case["last_response"] = last.get(r.name, {}).get("response")
			case["open"] = r.case_status in TREATING_STATUSES
			case["concern"] = concern(case, case["last_treatment_on"])
			files.append(case)

		return {
			"ok": True,
			"from": str(start),
			"to": str(end),
			"cases": files,
			"counts": counts,
			"truncated": len(rows) >= PAGE,
			"statuses": {"open": list(TREATING_STATUSES), "closed": list(CLOSED_STATUSES)},
			# The lines the farm has drawn, so the page explains its own flags
			# rather than hardcoding a number that is a setting.
			"concern_days": concern_days(),
			"stale_days": stale_days(),
			"months": _months(start, end),
		}

	return run(go, "livestock health_cases failed")


def _names(d, start, end):
	"""The case names this window and these filters ask for.

	One SQL pass, because the window is an OR and `frappe.get_all` filters are
	an AND. A file opened in March and still open in June belongs in June's
	register even though it is not one of June's openings — and dropping that
	arm is exactly what would make the register quietly forget the cow who has
	been under treatment since March.
	"""
	conditions = ["docstatus = 1"]
	params = {"start": str(start), "end": str(end)}
	if d.get("animal"):
		conditions.append("animal = %(animal)s")
		params["animal"] = d["animal"]
	if d.get("herd"):
		conditions.append("current_herd = %(herd)s")
		params["herd"] = d["herd"]

	status = (d.get("status") or "").strip()
	if status == "open":
		# Open is open, whenever it started. A ward round does not have a date
		# range on it.
		conditions.append("case_status IN %(treating)s")
		params["treating"] = tuple(TREATING_STATUSES)
		window = ""
	elif status == "closed":
		conditions.append("case_status IN %(closed)s")
		params["closed"] = tuple(CLOSED_STATUSES)
		window = " AND (opened_date BETWEEN %(start)s AND %(end)s OR closed_date BETWEEN %(start)s AND %(end)s)"
	elif status:
		conditions.append("case_status = %(status)s")
		params["status"] = status
		window = " AND opened_date BETWEEN %(start)s AND %(end)s"
	else:
		params["treating"] = tuple(TREATING_STATUSES)
		window = (
			" AND ((opened_date BETWEEN %(start)s AND %(end)s)"
			" OR (closed_date BETWEEN %(start)s AND %(end)s)"
			" OR (case_status IN %(treating)s AND opened_date <= %(end)s))"
		)

	rows = frappe.db.sql(
		"""SELECT name FROM `tabLivestock Health Case`
		   WHERE {conditions}{window}
		   ORDER BY opened_date DESC, creation DESC
		   LIMIT {page}""".format(
			conditions=" AND ".join(conditions), window=window, page=PAGE
		),
		params,
		pluck="name",
	)
	return rows


def _last_treatments(names):
	"""Per case: how many treatments, the latest date, and the latest response."""
	if not names:
		return {}
	rows = frappe.db.sql(
		"""SELECT parent, COUNT(*) AS n, MAX(treatment_date) AS last_on
		   FROM `tabLivestock Health Treatment`
		   WHERE parenttype = 'Livestock Health Case' AND parent IN %(names)s
		   GROUP BY parent""",
		{"names": tuple(names)},
		as_dict=True,
	)
	out = {r.parent: {"count": int(r.n), "on": str(r.last_on) if r.last_on else None} for r in rows}
	latest = frappe.db.sql(
		"""SELECT t.parent, t.response_observed, t.treatment_date
		   FROM `tabLivestock Health Treatment` t
		   WHERE t.parenttype = 'Livestock Health Case' AND t.parent IN %(names)s
		     AND IFNULL(t.response_observed, '') != ''
		   ORDER BY t.treatment_date DESC, t.idx DESC""",
		{"names": tuple(names)},
		as_dict=True,
	)
	for row in latest:
		entry = out.setdefault(row.parent, {"count": 0, "on": None})
		entry.setdefault("response", row.response_observed)
	return out


def _counts(rows):
	"""The four numbers a manager asks for before reading any file."""
	open_now = [r for r in rows if r.case_status in TREATING_STATUSES]
	return {
		"total": len(rows),
		"open": len(open_now),
		"closed": len([r for r in rows if r.case_status in CLOSED_STATUSES]),
		"recovered": len([r for r in rows if r.case_status == "Recovered"]),
		"died": len([r for r in rows if r.case_status in ("Died", "Culled")]),
		"lost_kg": flt(sum(flt(r.production_loss_kg) for r in rows)),
		"cost": flt(sum(flt(r.total_treatment_cost) for r in rows)),
	}


def _months(start, end):
	"""The window as a list of months, so the page can draw a bar per month."""
	out = []
	cursor = getdate(start).replace(day=1)
	last = getdate(end).replace(day=1)
	while cursor <= last and len(out) < 60:
		out.append(str(cursor)[:7])
		cursor = getdate(add_days(cursor, 32)).replace(day=1)
	return out
