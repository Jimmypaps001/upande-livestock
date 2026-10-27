"""What the six dashboard reads share.

`_is_active` used to live here as a fourth, slightly different answer to "which
animals count as live livestock" — it listed "Deceased" and "Disposed", which
are not Animal.status options, and omitted "Transferred Out", which is. The
dashboard would therefore have counted an animal that left the farm as active
stock. It now imports `common.choices.is_active`, so the dashboard and the
data-entry dropdowns cannot drift apart.
"""

import frappe
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.common.animal import live_herd_count
from upande_livestock.serverscripts.common.choices import RETIRED_STATUSES
from upande_livestock.serverscripts.common.health_case import TREATING_STATUSES
from upande_livestock.serverscripts.performance.bull_performance import (
	DEFAULT_PERIOD_DAYS,
	PERFORMANCE_CLASSES,
	active_animals,
	herd_rows,
)

# Chronic is a way a case ENDS (common.health_case.CLOSED_STATUSES); counting it
# open kept every case closed as Chronic on the dashboard for good.
_OPEN_CASE_STATUS = TREATING_STATUSES


def _active_animal_count() -> float:
	placeholders = ", ".join(["%s"] * len(RETIRED_STATUSES))
	return flt(
		frappe.db.sql(
			f"""SELECT COUNT(*) FROM `tabAnimal`
			    WHERE IFNULL(disabled, 0) = 0
			      AND IFNULL(status, '') NOT IN ({placeholders})""",
			RETIRED_STATUSES,
		)[0][0]
	)


def _herd_labels() -> dict:
	"""Map Herds.name -> display label (herd_name, falling back to name)."""
	return {h.name: (h.herd_name or h.name) for h in frappe.get_all("Herds", fields=["name", "herd_name"])}


def _zeros() -> dict:
	return {
		"kpis": {
			"active_animals": 0,
			"herds_count": 0,
			"health_events": 0,
			"births": 0,
		},
		"herds": [],
		"beef": {"herds": [], "weighings_overdue": 0, "band_moves_due": 0, "ready_for_exit": 0},
	}


def _open_alerts(kind) -> int:
	return frappe.db.count("Livestock Alert", {"alert_kind": kind, "status": "Open"})


def _beef() -> dict:
	"""The beef tiles: per performance herd, and the open weight alerts.

	Counts are the OPEN Livestock Alerts of the three weight kinds — the alert
	engine already decides who is overdue, due a band move or ready to leave,
	and a second opinion computed here could only disagree with it.
	"""
	herds = []
	for h in frappe.get_all(
		"Herds",
		filters={"herd_class": ["in", PERFORMANCE_CLASSES]},
		fields=["name", "herd_class"],
		order_by="herd_class asc, name asc",
	):
		rows = herd_rows(h.name, active_animals(h.name), DEFAULT_PERIOD_DAYS)
		weights = [r["latest_weight_kg"] for r in rows if r["latest_weight_kg"] is not None]
		gains = [r["period_adg"] for r in rows if r["period_adg"] is not None]
		herds.append(
			{
				"herd": h.name,
				"herd_class": h.herd_class,
				"head_count": len(rows),
				"avg_weight_kg": round(sum(weights) / len(weights), 1) if weights else None,
				"avg_adg_kg": round(sum(gains) / len(gains), 3) if gains else None,
			}
		)
	return {
		"herds": herds,
		"weighings_overdue": _open_alerts("Weighing Overdue"),
		"band_moves_due": _open_alerts("Weight Band Move Due"),
		"ready_for_exit": _open_alerts("Ready for Exit"),
	}


def _build() -> dict:
	out = _zeros()
	k = out["kpis"]

	# ---- KPI: active animals + distinct herds ----------------------------
	k["active_animals"] = _active_animal_count()
	k["herds_count"] = flt(
		frappe.db.sql(
			"""SELECT COUNT(DISTINCT current_herd) FROM `tabAnimal`
			   WHERE IFNULL(current_herd, '') != ''"""
		)[0][0]
	)

	# ---- KPI: health events this week ------------------------------------
	week_ago = add_days(today(), -7)
	k["health_events"] = flt(
		frappe.db.count("Livestock Health Case", {"opened_date": [">=", week_ago], "docstatus": 1})
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

	# ---- Herd tiles -------------------------------------------------------
	herds = frappe.get_all(
		"Herds",
		fields=["name", "herd_name"],
		order_by="number_of_animals desc",
		limit_page_length=12,
	)
	for h in herds:
		hid = h["name"]
		animals = flt(live_herd_count(hid))
		pregnant = flt(
			frappe.db.sql(
				"""SELECT COUNT(*) FROM `tabAnimal`
				   WHERE current_herd = %s AND LOWER(IFNULL(repro_status,'')) LIKE '%%pregn%%'""",
				(hid,),
			)[0][0]
		)
		out["herds"].append(
			{
				"name": h.get("herd_name") or hid,
				"animals": animals,
				"pregnant": pregnant,
			}
		)

	out["beef"] = _beef()
	return out
