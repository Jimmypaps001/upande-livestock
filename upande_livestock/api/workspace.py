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
from frappe.utils import add_days, flt, today

# Animal.status values that should NOT count as "active" livestock.
_INACTIVE_STATUS = ("Dead", "Deceased", "Sold", "Culled", "Disposed")


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
		frappe.db.count("Animal Health Case", {"opened_date": [">=", week_ago]})
	)

	# ---- KPI: births this month ------------------------------------------
	month_start = today()[:8] + "01"
	k["births"] = flt(
		frappe.db.sql(
			"""SELECT COUNT(*) FROM `tabAnimal Event`
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
