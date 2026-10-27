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

	return out
