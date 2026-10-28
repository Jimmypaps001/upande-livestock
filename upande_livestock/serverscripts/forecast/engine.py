"""Pure forecasting engine for beef production (stdlib only, no frappe imports)."""
import math
from collections import defaultdict
from datetime import date, timedelta

FARM_KEY = "__farm__"


def iso_week_start(d):
	return d - timedelta(days=d.weekday())


def forecast_adg(own, herd_avg, herd_target, farm_target):
	"""First value that is not None and > 0 wins."""
	for value, source in ((own, "own"), (herd_avg, "herd"), (herd_target, "herd_target"), (farm_target, "farm_target")):
		if value is not None and value > 0:
			return value, source
	return None, "none"


def project_weight(latest_kg, latest_date, adg, on):
	return latest_kg + adg * (on - latest_date).days


def ready_date(latest_kg, latest_date, adg, exit_kg, today):
	if latest_kg >= exit_kg:
		return today
	if adg is None or adg <= 0:
		return None
	days = math.ceil((exit_kg - latest_kg) / adg)
	return max(latest_date + timedelta(days=days), today)


def weekly_output(bulls, today, weeks):
	start = iso_week_start(today)
	rows = [{"week_start": start + timedelta(weeks=i), "head": 0, "kg": 0.0, "animals": []} for i in range(weeks)]
	by_week = {r["week_start"]: r for r in rows}
	for b in bulls:
		ready = ready_date(b["latest_kg"], b["latest_date"], b["adg"], b["exit_kg"], today)
		if ready is None:
			continue
		row = by_week.get(iso_week_start(ready))
		if row is None:
			continue
		if b["adg"] is None:
			kg = b["latest_kg"]  # already at/over exit weight; no projection possible
		else:
			kg = max(b["latest_kg"], project_weight(b["latest_kg"], b["latest_date"], b["adg"], ready))
		row["head"] += 1
		row["kg"] += kg
		row["animals"].append(b["animal"])
	for r in rows:
		r["kg"] = round(r["kg"], 1)
	return rows


def cover(output, commitments):
	committed = defaultdict(lambda: [0, 0.0])
	for c in commitments:
		slot = committed[c["week_start"]]
		slot[0] += c.get("head") or 0
		slot[1] += c.get("kg") or 0
	rows = []
	carry = 0
	for o in output:
		c_head, c_kg = committed.get(o["week_start"], (0, 0.0))
		available = o["head"] + carry
		balance = available - c_head
		if balance > 0:
			status = "Surplus"
		elif balance < 0:
			status = "Gap"
		elif c_head > 0 or o["head"] > 0:
			status = "Covered"
		else:
			status = "Idle"
		rows.append({
			"week_start": o["week_start"],
			"ready_head": o["head"],
			"ready_kg": o["kg"],
			"committed_head": c_head,
			"committed_kg": c_kg,
			"carry_in_head": carry,
			"available_head": available,
			"balance_head": balance,
			"status": status,
		})
		carry = max(balance, 0)
	return rows


def error_pct(actual, forecast):
	if actual is None or not forecast:
		return None
	return round((actual - forecast) / forecast, 4)


def trend_buckets(points, today, weeks):
	"""Interval ADG between consecutive weighings, bucketed by ISO week of the later weighing."""
	last = iso_week_start(today)
	first = last - timedelta(weeks=weeks - 1)
	by_animal = defaultdict(list)
	for animal, herd, d, kg in points:
		by_animal[animal].append((d, herd, kg))

	# (herd_key, week) -> {animal: [adgs]}, plus weights
	cells = defaultdict(lambda: {"adg": [], "kg": [], "animals": set()})
	for animal, pts in by_animal.items():
		pts.sort(key=lambda p: p[0])
		for (d0, _h0, kg0), (d1, h1, kg1) in zip(pts, pts[1:]):
			days = (d1 - d0).days
			if days <= 0:
				continue
			wk = iso_week_start(d1)
			if not first <= wk <= last:
				continue
			adg = (kg1 - kg0) / days
			for key in (h1, FARM_KEY):
				cell = cells[(key, wk)]
				cell["adg"].append(adg)
				cell["kg"].append(kg1)
				cell["animals"].add(animal)

	rows = []
	for (herd, wk) in sorted(cells, key=lambda k: (k[0] == FARM_KEY, str(k[0]), k[1])):
		cell = cells[(herd, wk)]
		rows.append({
			"week_start": wk,
			"herd": herd,
			"avg_adg": round(sum(cell["adg"]) / len(cell["adg"]), 4),
			"head": len(cell["animals"]),
			"avg_weight": round(sum(cell["kg"]) / len(cell["kg"]), 1),
		})
	return rows
