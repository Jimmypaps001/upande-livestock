# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Live stats for the Upande Livestock desk workspace (Overview dashboard).

Backs the ``Livestock Dashboard`` Custom HTML Block. The block's script calls
``get_livestock_workspace_stats`` once on load and renders the KPI cards, the
30-day milk-yield chart, the Top Herds list and the herd tiles from the single
JSON payload returned here.

All reads are defensive: the whole body is wrapped so the endpoint never raises
to the client, and thin/empty data (e.g. only a couple of Milk Recordings)
degrades to zeros / empty lists rather than an error.
"""

import frappe
from frappe.utils import add_days, add_months, flt, get_first_day, today

# Animal.status values that should NOT count as "active" livestock.
_INACTIVE_STATUS = ("Dead", "Deceased", "Sold", "Culled", "Disposed")

# Health-case statuses treated as still open / needing attention.
_OPEN_CASE_STATUS = ("Open", "Under Treatment", "Chronic")


def _herd_labels() -> dict:
	"""Map Herds.name -> display label (herd_name, falling back to name)."""
	return {
		h.name: (h.herd_name or h.name)
		for h in frappe.get_all("Herds", fields=["name", "herd_name"])
	}


def _zeros() -> dict:
	return {
		"kpis": {
			"active_animals": 0,
			"herds_count": 0,
			"milk_value": 0.0,
			"milk_date": None,
			"health_events": 0,
			"births": 0,
		},
		"milk_series": [],
		"top_herds": [],
		"herds": [],
	}


@frappe.whitelist()
def get_livestock_workspace_stats() -> dict:
	try:
		return _build()
	except Exception:
		frappe.log_error(title="livestock workspace stats failed")
		out = _zeros()
		out["error"] = "Could not load livestock stats."
		return out


def _build() -> dict:
	out = _zeros()
	k = out["kpis"]

	# ---- KPI: active animals + distinct herds ----------------------------
	placeholders = ", ".join(["%s"] * len(_INACTIVE_STATUS))
	k["active_animals"] = flt(
		frappe.db.sql(
			f"""SELECT COUNT(*) FROM `tabAnimal`
			    WHERE IFNULL(status, '') NOT IN ({placeholders})""",
			_INACTIVE_STATUS,
		)[0][0]
	)
	k["herds_count"] = flt(
		frappe.db.sql(
			"""SELECT COUNT(DISTINCT current_herd) FROM `tabAnimal`
			   WHERE IFNULL(current_herd, '') != ''"""
		)[0][0]
	)

	# ---- KPI: milk production (latest recording date total) --------------
	milk_latest = frappe.db.sql(
		"""SELECT recording_date, SUM(net_yield_kg)
		   FROM `tabMilk Recording`
		   WHERE recording_date = (SELECT MAX(recording_date) FROM `tabMilk Recording`)
		   GROUP BY recording_date"""
	)
	if milk_latest:
		k["milk_date"] = str(milk_latest[0][0])
		k["milk_value"] = flt(milk_latest[0][1])

	# ---- KPI: health events this week ------------------------------------
	week_ago = add_days(today(), -7)
	k["health_events"] = flt(
		frappe.db.count("Livestock Health Case", {"opened_date": [">=", week_ago]})
	)

	# ---- KPI: births this month ------------------------------------------
	month_start = today()[:8] + "01"
	k["births"] = flt(
		frappe.db.sql(
			"""SELECT COUNT(*) FROM `tabLivestock Event`
			   WHERE event_date >= %s
			     AND (LOWER(event_type) LIKE '%%calv%%' OR LOWER(event_type) LIKE '%%birth%%')""",
			(month_start,),
		)[0][0]
	)

	# ---- Milk yield · last 30 days ---------------------------------------
	series = frappe.db.sql(
		"""SELECT recording_date, SUM(net_yield_kg)
		   FROM `tabMilk Recording`
		   WHERE recording_date >= %s
		   GROUP BY recording_date
		   ORDER BY recording_date""",
		(add_days(today(), -30),),
		as_dict=False,
	)
	out["milk_series"] = [{"date": str(d), "yield": flt(y)} for d, y in series]

	# ---- Top Herds by yield (last 30 days) -------------------------------
	top = frappe.db.sql(
		"""SELECT herd, SUM(net_yield_kg) AS y
		   FROM `tabMilk Recording`
		   WHERE recording_date >= %s AND IFNULL(herd, '') != ''
		   GROUP BY herd ORDER BY y DESC LIMIT 5""",
		(add_days(today(), -30),),
		as_dict=True,
	)
	out["top_herds"] = [{"name": r.herd, "yield": flt(r.y)} for r in top]

	# ---- Herd tiles -------------------------------------------------------
	herds = frappe.get_all(
		"Herds",
		fields=["name", "herd_name"],
		order_by="number_of_animals desc",
		limit_page_length=12,
	)
	# latest net-yield / cows-milked per herd, for an avg-per-cow figure
	latest_yield = {
		r.herd: (flt(r.net_yield_kg), flt(r.cows_milked))
		for r in frappe.db.sql(
			"""SELECT m.herd, m.net_yield_kg, m.cows_milked
			   FROM `tabMilk Recording` m
			   JOIN (SELECT herd, MAX(recording_date) rd FROM `tabMilk Recording`
			         GROUP BY herd) x
			     ON x.herd = m.herd AND x.rd = m.recording_date""",
			as_dict=True,
		)
	}
	for h in herds:
		hid = h["name"]
		animals = flt(frappe.db.count("Animal", {"current_herd": hid}))
		milkers = flt(
			frappe.db.sql(
				"""SELECT COUNT(*) FROM `tabAnimal`
				   WHERE current_herd = %s
				     AND (LOWER(IFNULL(repro_status,'')) LIKE '%%lact%%'
				          OR LOWER(IFNULL(status,'')) LIKE '%%lact%%'
				          OR IFNULL(days_in_milk,0) > 0)""",
				(hid,),
			)[0][0]
		)
		pregnant = flt(
			frappe.db.sql(
				"""SELECT COUNT(*) FROM `tabAnimal`
				   WHERE current_herd = %s AND LOWER(IFNULL(repro_status,'')) LIKE '%%pregn%%'""",
				(hid,),
			)[0][0]
		)
		ny, cm = latest_yield.get(hid, (0.0, 0.0))
		avg_yield = round(ny / cm, 1) if cm else 0.0
		out["herds"].append(
			{
				"name": h.get("herd_name") or hid,
				"animals": animals,
				"milkers": milkers,
				"pregnant": pregnant,
				"avg_yield": avg_yield,
			}
		)

	return out


# ======================================================================
# Per-tab endpoints. Each is lazy-fetched by the Custom HTML Block the
# first time its tab is opened, and every one degrades to empty lists /
# zeros rather than raising to the client (mirrors get_livestock_
# workspace_stats above).
# ======================================================================


@frappe.whitelist()
def get_animals() -> dict:
	"""Animals tab: a capped, searchable/filterable list plus summary
	counts and the option lists the client uses to build its filters."""
	try:
		herds = _herd_labels()
		rows = frappe.get_all(
			"Animal",
			fields=[
				"name", "tag_number", "burn_name", "sex", "species", "breed",
				"current_herd", "status", "repro_status", "days_in_milk", "parity",
			],
			order_by="tag_number asc",
			limit_page_length=1000,
		)
		for r in rows:
			r["herd_label"] = herds.get(r.get("current_herd") or "", r.get("current_herd") or "")
		active = [r for r in rows if (r.get("status") or "") not in _INACTIVE_STATUS]
		summary = {
			"total": len(rows),
			"active": len(active),
			"milking": sum(1 for r in rows if flt(r.get("days_in_milk")) > 0),
			"pregnant": sum(1 for r in rows if "pregn" in (r.get("repro_status") or "").lower()),
		}
		return {
			"rows": rows,
			"summary": summary,
			"capped": len(rows) >= 1000,
			"filters": {
				"herds": sorted({r["herd_label"] for r in rows if r.get("herd_label")}),
				"statuses": sorted({r["status"] for r in rows if r.get("status")}),
				"species": sorted({r["species"] for r in rows if r.get("species")}),
			},
		}
	except Exception:
		frappe.log_error(title="livestock get_animals failed")
		return {"rows": [], "summary": {}, "filters": {}, "error": "Could not load animals."}


@frappe.whitelist()
def get_production() -> dict:
	"""Production tab: recent Milk Recordings + 30-day quality/volume summary."""
	try:
		herds = _herd_labels()
		rows = frappe.get_all(
			"Milk Recording",
			fields=[
				"name", "recording_date", "session", "herd", "cows_milked",
				"total_yield_kg", "discarded_kg", "net_yield_kg", "fat_percent",
				"protein_percent", "bulk_scc", "milk_revenue",
			],
			order_by="recording_date desc, creation desc",
			limit_page_length=200,
		)
		for r in rows:
			r["herd_label"] = herds.get(r.get("herd") or "", r.get("herd") or "")
			r["recording_date"] = str(r["recording_date"]) if r.get("recording_date") else ""

		since = str(add_days(today(), -30))
		recent = [r for r in rows if r["recording_date"] and r["recording_date"] >= since]

		def _avg(key):
			vals = [flt(r.get(key)) for r in recent if r.get(key)]
			return round(sum(vals) / len(vals), 2) if vals else 0

		summary = {
			"records": len(recent),
			"net_kg": round(sum(flt(r.get("net_yield_kg")) for r in recent), 1),
			"revenue": round(sum(flt(r.get("milk_revenue")) for r in recent), 2),
			"avg_fat": _avg("fat_percent"),
			"avg_protein": _avg("protein_percent"),
			"avg_scc": _avg("bulk_scc"),
		}
		return {
			"rows": rows,
			"summary": summary,
			"filters": {
				"herds": sorted({r["herd_label"] for r in rows if r.get("herd_label")}),
				"sessions": sorted({r["session"] for r in rows if r.get("session")}),
			},
		}
	except Exception:
		frappe.log_error(title="livestock get_production failed")
		return {"rows": [], "summary": {}, "filters": {}, "error": "Could not load production."}


@frappe.whitelist()
def get_health() -> dict:
	"""Health tab: Livestock Health Cases (open first) + summary counts."""
	try:
		herds = _herd_labels()
		rows = frappe.get_all(
			"Livestock Health Case",
			fields=[
				"name", "animal", "animal_name", "current_herd", "opened_date",
				"case_status", "severity", "provisional_diagnosis",
				"confirmed_diagnosis", "vet_called", "is_zoonotic", "is_notifiable",
			],
			order_by="opened_date desc",
			limit_page_length=300,
		)
		# Stable sort keeps date order within the open / closed groups.
		rows.sort(key=lambda r: 0 if r.get("case_status") in _OPEN_CASE_STATUS else 1)
		for r in rows:
			r["herd_label"] = herds.get(r.get("current_herd") or "", r.get("current_herd") or "")
			r["opened_date"] = str(r["opened_date"]) if r.get("opened_date") else ""
			r["diagnosis"] = r.get("confirmed_diagnosis") or r.get("provisional_diagnosis") or ""
		summary = {
			"total": len(rows),
			"open": sum(1 for r in rows if r.get("case_status") in _OPEN_CASE_STATUS),
			"recovered": sum(1 for r in rows if r.get("case_status") == "Recovered"),
			"zoonotic": sum(1 for r in rows if r.get("is_zoonotic")),
			"notifiable": sum(1 for r in rows if r.get("is_notifiable")),
		}
		return {
			"rows": rows,
			"summary": summary,
			"filters": {
				"statuses": sorted({r["case_status"] for r in rows if r.get("case_status")}),
				"severities": sorted({r["severity"] for r in rows if r.get("severity")}),
			},
		}
	except Exception:
		frappe.log_error(title="livestock get_health failed")
		return {"rows": [], "summary": {}, "filters": {}, "error": "Could not load health cases."}


@frappe.whitelist()
def get_events() -> dict:
	"""Events tab: recent Livestock Events + counts by type."""
	try:
		herds = _herd_labels()
		rows = frappe.get_all(
			"Livestock Event",
			fields=[
				"name", "animal", "current_herd", "new_herd", "event_type",
				"event_date", "service_type", "service_status",
				"pregnancy_confirmation_status", "diagnosis_result",
			],
			order_by="event_date desc, creation desc",
			limit_page_length=300,
		)
		counts: dict = {}
		for r in rows:
			r["herd_label"] = herds.get(r.get("current_herd") or "", r.get("current_herd") or "")
			r["event_date"] = str(r["event_date"]) if r.get("event_date") else ""
			t = r.get("event_type") or "Other"
			counts[t] = counts.get(t, 0) + 1
		return {
			"rows": rows,
			"summary": {"total": len(rows), "by_type": counts},
			"filters": {"types": sorted({r["event_type"] for r in rows if r.get("event_type")})},
		}
	except Exception:
		frappe.log_error(title="livestock get_events failed")
		return {"rows": [], "summary": {}, "filters": {}, "error": "Could not load events."}


@frappe.whitelist()
def get_reports() -> dict:
	"""Reports tab: computed summary analytics (no single source doctype)."""
	try:
		this_start = get_first_day(today())
		next_start = add_months(this_start, 1)
		last_start = add_months(this_start, -1)

		def _milk_between(a, b):
			r = frappe.db.sql(
				"""SELECT IFNULL(SUM(net_yield_kg), 0), IFNULL(SUM(milk_revenue), 0)
				   FROM `tabMilk Recording`
				   WHERE recording_date >= %s AND recording_date < %s""",
				(a, b),
			)
			return flt(r[0][0]), flt(r[0][1])

		m_now_kg, m_now_rev = _milk_between(this_start, next_start)
		m_prev_kg, m_prev_rev = _milk_between(last_start, this_start)

		placeholders = ", ".join(["%s"] * len(_INACTIVE_STATUS))
		active = flt(
			frappe.db.sql(
				f"""SELECT COUNT(*) FROM `tabAnimal`
				    WHERE IFNULL(status, '') NOT IN ({placeholders})""",
				_INACTIVE_STATUS,
			)[0][0]
		)

		open_cases = flt(
			frappe.db.count("Livestock Health Case", {"case_status": ["in", list(_OPEN_CASE_STATUS)]})
		)
		cases_month = flt(frappe.db.count("Livestock Health Case", {"opened_date": [">=", this_start]}))

		def _repro(like):
			return flt(
				frappe.db.sql(
					"SELECT COUNT(*) FROM `tabAnimal` WHERE LOWER(IFNULL(repro_status, '')) LIKE %s",
					("%" + like + "%",),
				)[0][0]
			)

		pregnant, served, open_repro = _repro("pregn"), _repro("serv"), _repro("open")

		births = flt(
			frappe.db.sql(
				"""SELECT COUNT(*) FROM `tabLivestock Event`
				   WHERE event_date >= %s
				     AND (LOWER(event_type) LIKE '%%calv%%' OR LOWER(event_type) LIKE '%%birth%%')""",
				(this_start,),
			)[0][0]
		)

		herds = _herd_labels()
		herd_rows = frappe.db.sql(
			"""SELECT current_herd AS h, COUNT(*) AS c FROM `tabAnimal`
			   WHERE IFNULL(current_herd, '') != ''
			   GROUP BY current_herd ORDER BY c DESC LIMIT 8""",
			as_dict=True,
		)
		herd_cmp = [{"name": herds.get(r.h, r.h), "animals": int(r.c)} for r in herd_rows]

		return {
			"production": {
				"month_kg": round(m_now_kg, 1),
				"prev_kg": round(m_prev_kg, 1),
				"delta_kg": round(m_now_kg - m_prev_kg, 1),
				"month_rev": round(m_now_rev, 2),
				"prev_rev": round(m_prev_rev, 2),
			},
			"health": {
				"active_animals": active,
				"open_cases": open_cases,
				"cases_month": cases_month,
				"open_rate": round(open_cases / active * 100, 1) if active else 0,
			},
			"reproduction": {
				"pregnant": pregnant,
				"served": served,
				"open": open_repro,
				"births_month": births,
				"preg_rate": round(pregnant / active * 100, 1) if active else 0,
			},
			"herds": herd_cmp,
		}
	except Exception:
		frappe.log_error(title="livestock get_reports failed")
		return {
			"production": {}, "health": {}, "reproduction": {}, "herds": [],
			"error": "Could not load reports.",
		}
