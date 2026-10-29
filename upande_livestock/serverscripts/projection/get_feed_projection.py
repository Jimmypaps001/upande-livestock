# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Feed projection: what the herds eat a day, what they will eat over the next weeks, and how long
the feed in store lasts. Maths in engine.py; reads in data.py."""

import frappe
from frappe.utils import add_days, getdate, today

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.projection import data, engine

MIN_WEEKS, MAX_WEEKS, DEFAULT_WEEKS = 4, 26, 12


def clamp_weeks(weeks):
	try:
		w = int(weeks)
	except (TypeError, ValueError):
		w = DEFAULT_WEEKS
	return max(MIN_WEEKS, min(MAX_WEEKS, w))


def _week_rows(rows, start):
	return [{
		"week": r["week"], "week_start": str(add_days(start, 7 * (r["week"] - 1))),
		"feed_kg": round(r["feed_kg"], 1), "cumulative_kg": round(r["cumulative_kg"], 1), "head": r["head"],
		"exits": r["exits"], "avg_kg": None if r["avg_kg"] is None else round(r["avg_kg"], 1),
		"live_kg": round(r["live_kg"], 1),
	} for r in rows]


def _days(x):
	return None if x is None else round(x, 1)


def build(on, weeks, herd=None):
	cfg = data.settings()
	pct = cfg["dm_intake_pct"]
	animals, summaries = data.animals_and_herds(on, herd)
	bands = [{"herd": b["herd"], "min_kg": b["min_kg"], "max_kg": b["max_kg"]}
	         for b in data.fattening_bands()] if not herd else None
	proj = engine.project(animals, weeks, pct, bands)
	stock = data.feed_stock()
	start = getdate(on)

	need = {h: proj["herds"].get(h, {}).get("day_kg", 0.0) for h in summaries}
	own = {h: stock["paddock_kg"].get(summaries[h]["paddock"], 0.0) for h in summaries}
	stock_by_herd = engine.split_stock(stock["central_kg"], need, own)
	herd_rows = []
	for name, s in summaries.items():
		p = proj["herds"].get(name)
		row = dict(s)
		if p:
			row.update({"live_kg": round(p["live_kg"], 1), "avg_kg": round(p["live_kg"] / max(1, p["head"]), 1),
			            "day_kg": round(p["day_kg"], 1), "projected_head": p["head"]})
			row["weeks"] = {sc: _week_rows(p[sc]["weeks"], start) for sc in engine.SCENARIOS}
			held = stock_by_herd.get(name, 0.0)
			row["stock_kg"] = round(held, 1)
			row["paddock_stock_kg"] = round(stock["paddock_kg"].get(s["paddock"], 0.0), 1) if s["paddock"] else 0.0
			row["days_left"] = {sc: _days(engine.days_of_feed(held, p[sc]["weeks"])) for sc in engine.SCENARIOS}
			row["days_left"]["today_rate"] = _days(engine.days_at_rate(held, p["day_kg"]))
		else:
			row.update({"live_kg": 0, "avg_kg": None, "day_kg": 0, "projected_head": 0, "weeks": None,
			            "stock_kg": 0, "paddock_stock_kg": 0, "days_left": None})
		herd_rows.append(row)

	t = proj["total"]
	total = {
		"head": sum(s["head"] for s in summaries.values()),
		"fed_heads": sum(s["fed_heads"] for s in summaries.values()),
		"calves": sum(s["calves"] for s in summaries.values()),
		"live_kg": round(t["live_kg"], 1), "day_kg": round(t["day_kg"], 1),
		"weeks": {sc: _week_rows(t[sc]["weeks"], start) for sc in engine.SCENARIOS},
		"stock_kg": round(stock["total_kg"], 1),
		"days_left": {sc: _days(engine.days_of_feed(stock["total_kg"], t[sc]["weeks"])) for sc in engine.SCENARIOS},
	}
	total["days_left"]["today_rate"] = _days(engine.days_at_rate(stock["total_kg"], t["day_kg"]))
	band_block = None
	if proj["bands"]:
		b = proj["bands"]
		band_block = {"names": [x["herd"] for x in bands], "today": b["today"],
		              "weeks": [dict(w, week_start=str(add_days(start, 7 * (w["week"] - 1)))) for w in b["weeks"]]}
	return {
		"as_of": str(start), "weeks": weeks, "settings": cfg, "total": total, "herds": herd_rows,
		"bands": band_block,
		"stock": {"total_kg": round(stock["total_kg"], 1), "central_kg": round(stock["central_kg"], 1),
		          "items": [dict(i, kg=round(i["kg"], 1)) for i in stock["items"]],
		          "warehouses": [dict(w, kg=round(w["kg"], 1)) for w in stock["warehouses"]],
		          "uncounted": stock["uncounted"]},
		"notes": [
			"Intake is {}% of live weight a day; stock is counted in kg as stored (no moisture correction).".format(pct),
			"Gain is {}-{} kg/day in the low and high cases; an animal with {}+ weighings over {}+ days uses its own gain.".format(
				cfg["adg_min_kg"], cfg["adg_max_kg"], cfg["min_weighings"], cfg["min_span_days"]),
			"Herds with no target gain (mature cows) are held at today's weight. Feedlot animals leave at the exit "
			"weight and are not replaced.",
			"Calves still with their dams are counted in head but not fed.",
		],
	}


@frappe.whitelist()
def get_feed_projection(weeks=None, herd=None) -> dict:
	guard_read("Animal")
	return build(today(), clamp_weeks(weeks), herd or None)
