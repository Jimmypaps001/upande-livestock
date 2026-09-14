"""The dashboard's report tab: production, health, reproduction and herd rollups.

Read-guarded on Animal."""

import frappe
from frappe.utils import add_months, flt, get_first_day, today

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.dashboard._shared import (
	_OPEN_CASE_STATUS,
	_active_animal_count,
	_herd_labels,
)


@frappe.whitelist()
def get_reports() -> dict:
	"""Reports tab: computed summary analytics (no single source doctype)."""
	guard_read("Animal")
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

		active = _active_animal_count()

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
		# COUNTED THE SAME WAY THE HERD RECORD AND THE FEED RUN COUNT. A disposal
		# sets the animal's status and leaves `current_herd` alone on purpose, so
		# a plain COUNT(*) here reported sold and dead animals as still standing
		# in their old herd — 112 bullying heifers against the herd screen's 94,
		# and a "Not In Count" holding pen showing 57 head that are not on the
		# farm at all. `common/animal.live_herd_count` is the one rule; this is
		# the same filter in SQL because it wants every herd in one query.
		herd_rows = frappe.db.sql(
			"""SELECT current_herd AS h, COUNT(*) AS c FROM `tabAnimal`
			   WHERE IFNULL(current_herd, '') != ''
			     AND docstatus != 2
			     AND IFNULL(status, '') NOT IN %(retired)s
			   GROUP BY current_herd ORDER BY c DESC LIMIT 8""",
			{"retired": tuple(RETIRED_STATUSES)},
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
			"production": {},
			"health": {},
			"reproduction": {},
			"herds": [],
			"error": "Could not load reports.",
		}
