# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The one place livestock reaches into upande_production.

Production owns the machines (asset allocation) and silage making; livestock
only reads what they cost. The two apps do not import each other: Kaitet runs
livestock without production, and livestock must not break there. So every
call here is

* asked only when ``"upande_production" in frappe.get_installed_apps()``,
* made through ``frappe.get_attr`` on the dotted path, never an import, and
* caught whole — a production function that is missing, renamed, refuses the
  user or fails answers "not available", and the cost page goes on without
  fuel rather than going down with it.

An answer that is not available is said so (`available: False` and a reason),
never reported as zero fuel: a zero would claim the tractors burned nothing.
"""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.costing._maths import as_date

APP = "upande_production"
# Production's logic functions, not its whitelisted endpoints: the endpoints
# guard on production's own roles (or Stock Entry read), which a livestock
# manager does not hold, so every farm user would read "fuel not available".
# The livestock endpoint that asks has already checked its own user, and only
# the costs come back, not production's records.
ALLOCATION_COSTS = "upande_production.production.logic.asset_allocation.allocation_costs"
SILAGE_COST_SUMMARY = "upande_production.production.logic.silage.cost_summary"


def installed() -> bool:
	try:
		return APP in frappe.get_installed_apps()
	except Exception:
		return False


def _call(path, **kwargs):
	"""(answer, reason). The answer is None when production cannot give one."""
	if not installed():
		return None, "upande_production is not installed."
	try:
		fn = frappe.get_attr(path)
	except Exception:
		return None, "upande_production does not offer this yet."
	try:
		out = fn(**kwargs)
	except Exception:
		frappe.log_error(title=f"livestock costing: {path} failed")
		return None, "upande_production could not answer."
	if isinstance(out, dict) and out.get("error"):
		return None, str(out["error"])
	return out, None


def fuel(from_date, to_date, cost_centers):
	"""Diesel charged to the livestock cost centres, by day, and the machine work behind it.

	Returns {available, reason, by_day: {date: cost}, litres_by_day, machines: [...]}.
	One call per cost centre: an allocation names one centre, so the rows
	never overlap, but they are de-duplicated by allocation all the same in
	case production ever answers a centre's children with its parent.
	"""
	out = {"available": False, "reason": None, "by_day": {}, "litres_by_day": {}, "machines": []}
	if not installed():
		out["reason"] = "upande_production is not installed."
		return out
	if not cost_centers:
		out["reason"] = "No livestock cost centre is set, so no machine work can be matched to the herds."
		return out
	seen = set()
	for cc in cost_centers:
		answer, reason = _call(ALLOCATION_COSTS, from_date=str(from_date), to_date=str(to_date), cost_center=cc)
		if answer is None:
			out.update(available=False, reason=reason, by_day={}, litres_by_day={}, machines=[])
			return out
		for d in answer.get("days") or []:
			if not d.get("date"):
				continue
			day = as_date(d["date"])
			out["by_day"][day] = out["by_day"].get(day, 0.0) + flt(d.get("diesel_cost"))
			out["litres_by_day"][day] = out["litres_by_day"].get(day, 0.0) + flt(d.get("diesel_litres"))
		for r in answer.get("rows") or []:
			key = r.get("allocation") or id(r)
			if key in seen:
				continue
			seen.add(key)
			out["machines"].append({
				"allocation": r.get("allocation"),
				"machine": r.get("machine"),
				"operator": r.get("operator"),
				"operator_name": r.get("operator_name"),
				"start_time": str(r.get("start_time") or "") or None,
				"end_time": str(r.get("end_time") or "") or None,
				"duration_hours": flt(r.get("duration_hours"), 2),
				"diesel_litres": flt(r.get("diesel_litres"), 2),
				"diesel_cost": flt(r.get("diesel_cost"), 2),
				"cost_center": r.get("cost_center"),
			})
	out["available"] = True
	out["machines"].sort(key=lambda m: m.get("start_time") or "")
	return out


def _pick(row, *keys):
	for k in keys:
		if row.get(k) not in (None, ""):
			return row.get(k)
	return None


def silage(from_date, to_date):
	"""Silage cost per kg from production's cycles: {available, reason, cycles: [...]}.

	Production's answer is read loosely — a bare list or {cycles: [...]}, and
	a few likely names for each figure — and passed on in one fixed shape, so
	a renamed key over there blanks a cell here instead of breaking the page.
	"""
	answer, reason = _call(SILAGE_COST_SUMMARY, from_date=str(from_date), to_date=str(to_date))
	if answer is None:
		return {"available": False, "reason": reason, "cycles": []}
	rows = answer if isinstance(answer, list) else (answer.get("cycles") or answer.get("rows") or [])
	cycles = []
	for r in rows:
		if not isinstance(r, dict):
			continue
		kg = flt(_pick(r, "ensiled_kg", "kg"))
		total = _pick(r, "total_cost", "cost")
		per_kg = _pick(r, "cost_per_kg")
		if per_kg is None and total is not None and kg:
			per_kg = flt(total) / kg
		cycles.append({
			"cycle": _pick(r, "cycle", "name", "silage_cycle"),
			"crop": _pick(r, "crop"),
			"silage_item": _pick(r, "silage_item", "item"),
			"status": _pick(r, "status"),
			"ensiled_kg": kg,
			"total_cost": flt(total, 2) if total is not None else None,
			"cost_per_kg": flt(per_kg, 4) if per_kg is not None else None,
		})
	return {"available": True, "reason": None, "cycles": cycles}
