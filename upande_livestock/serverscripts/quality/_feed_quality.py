# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Milk quality set beside what each milking herd is fed.

Quality is the lab figures on each Milk Recording (fat, protein, bulk tank
SCC). Feed is the herd's ration — its standing recipe, read off the Herds BOM:
kilograms a head a day, how much of it is concentrate — and what was actually
issued to it in the window. A ration trial (one herd on a different recipe)
shows here as that herd's figures against the rest of the milking herds.
"""

import frappe
from frappe.utils import add_days, flt, getdate, today

from upande_livestock.serverscripts.common.herd_movement import milking_herds
from upande_livestock.serverscripts.feeding import _engine as feeding

WINDOWS = (30, 90, 150)


def _ration(herd):
	bom_no = frappe.db.get_value("Herds", herd, "bom")
	if not bom_no:
		return None
	bom = frappe.get_doc("BOM", bom_no)
	bought_in = feeding._bought_in_concentrates()
	lines = []
	for row in bom.items:
		lines.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name or row.item_code,
				"qty": flt(row.qty),
				"uom": row.uom,
				"concentrate": bool(feeding._sub_bom_for(row) or row.item_code in bought_in),
			}
		)
	# Kilograms only: a bale of hay in the same sum would not be a weight.
	kg = [ln for ln in lines if (ln["uom"] or "").lower() in ("kg", "kilogram", "kgs")]
	conc = sum(ln["qty"] for ln in kg if ln["concentrate"])
	total = sum(ln["qty"] for ln in kg)
	return {
		"bom": bom.name,
		"name": frappe.db.get_value("Item", bom.item, "item_name") or bom.item,
		"per_head": flt(bom.quantity),
		"uom": bom.uom,
		"concentrate_kg": round(conc, 2),
		"concentrate_share": round(conc / total, 3) if total else None,
		"lines": sorted(lines, key=lambda ln: -ln["qty"]),
	}


def _fed(herd, start, end):
	"""What left the store for this herd in the window, from the feed issues."""
	row = frappe.db.sql(
		"""SELECT COUNT(DISTINCT se.name) runs, IFNULL(SUM(sed.qty), 0) kg
		   FROM `tabStock Entry` se JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
		   WHERE se.docstatus = 1 AND se.purpose = 'Material Issue'
		     AND se.remarks LIKE %(herd)s AND se.posting_date BETWEEN %(s)s AND %(e)s""",
		{"herd": f"Animal feeding - {herd} - %", "s": start, "e": end},
		as_dict=True,
	)[0]
	return {"runs": int(row.runs or 0), "kg": round(flt(row.kg), 1)}


def _milk(herd, start, end):
	return frappe.db.sql(
		"""SELECT recording_date, cows_milked, net_yield_kg, fat_percent, protein_percent, bulk_scc
		   FROM `tabMilk Recording`
		   WHERE docstatus = 1 AND herd = %s AND recording_date BETWEEN %s AND %s
		   ORDER BY recording_date""",
		(herd, start, end),
		as_dict=True,
	)


def _mean(values):
	values = [flt(v) for v in values if flt(v) > 0]
	return round(sum(values) / len(values), 3) if values else None


def _quality(rows):
	cows_by_day, kg = {}, 0.0
	for r in rows:
		kg += flt(r.net_yield_kg)
		cows_by_day[r.recording_date] = max(cows_by_day.get(r.recording_date, 0), int(r.cows_milked or 0))
	cow_days = sum(cows_by_day.values())
	return {
		"fat": _mean(r.fat_percent for r in rows),
		"protein": _mean(r.protein_percent for r in rows),
		"scc": _mean(r.bulk_scc for r in rows),
		"readings": sum(1 for r in rows if flt(r.fat_percent) or flt(r.protein_percent) or flt(r.bulk_scc)),
		"milkings": len(rows),
		"milk_per_cow_day": round(kg / cow_days, 2) if cow_days else None,
	}


def _week(day):
	day = getdate(day)
	return str(add_days(day, -day.weekday()))


def _pct(value, against):
	return round((value / against - 1) * 100, 1) if value and against else None


def feed_quality(days=90):
	days = int(days) if int(days or 0) in WINDOWS else 90
	end = getdate(today())
	start = getdate(add_days(end, -(days - 1)))

	herds, weeks = [], {}
	for herd in milking_herds():
		rows = _milk(herd, start, end)
		herds.append(
			{
				"herd": herd,
				"cows": int(frappe.db.count("Animal", {"current_herd": herd, "status": "Active"})),
				"ration": _ration(herd),
				"fed": _fed(herd, start, end),
				"quality": _quality(rows),
			}
		)
		by_week = {}
		for r in rows:
			by_week.setdefault(_week(r.recording_date), []).append(r)
		for wk, wrows in by_week.items():
			weeks.setdefault(wk, {})[herd] = {
				"fat": _mean(r.fat_percent for r in wrows),
				"protein": _mean(r.protein_percent for r in wrows),
				"scc": _mean(r.bulk_scc for r in wrows),
			}

	# Each herd against the other milking herds together: what a ration trial
	# is asked — is this herd's milk better than everyone else's?
	for h in herds:
		rest = [o["quality"] for o in herds if o is not h]
		for key in ("fat", "protein", "scc"):
			others = _mean(q[key] for q in rest)
			h.setdefault("vs_rest", {})[key] = _pct(h["quality"][key], others)

	return {
		"days": days,
		"from_date": str(start),
		"to_date": str(end),
		"windows": list(WINDOWS),
		"herds": herds,
		"weeks": [{"week": wk, "herds": weeks[wk]} for wk in sorted(weeks)],
	}
