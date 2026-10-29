"""Pure feed-projection maths (stdlib only, no frappe imports).

The rule: an animal eats `pct` % of its live weight a day (dry-matter intake),
and a growing animal gains `adg` kg a day. Weight on day d is kg + adg * d, so
the feed in a week is the intake at the weight half way through the days the
animal is still on the farm, times those days.

THREE SCENARIOS. Every animal carries a low, expected and high daily gain
(`adg_scenarios`): the settings' min and max bound the farm's range, and the
animal's own measured gain, when it has enough weighings, is the expected one
(widening the range for an animal that gains outside it). A herd that does not
grow (mature cows: no target gain) is held at today's weight in all three.

EXIT. A feedlot animal with an exit weight leaves the farm the day it reaches
it and is not replaced; one already at or over it leaves within the week. Its
feed stops with it, which is why the need falls toward the end of a long horizon.
"""

import math

SCENARIOS = ("low", "expected", "high")
WEEK = 7


def measured_adg(points, min_weighings, min_span_days):
	"""Gain over the whole weighing history, kg/day; None without enough of it.

	`points` is [(date, kg)]. "Not enough weighings" is None, never zero.
	"""
	pts = sorted(points)
	if len(pts) < max(2, int(min_weighings)):
		return None
	days = (pts[-1][0] - pts[0][0]).days
	if days <= 0 or days < min_span_days:
		return None
	return (pts[-1][1] - pts[0][1]) / days


def adg_scenarios(measured, herd_target, grows, min_adg, max_adg):
	"""{low, expected, high, source} daily gain for one animal."""
	if not grows:
		return {"low": 0, "expected": 0, "high": 0, "source": "flat"}
	if measured is not None:
		expected, source = measured, "measured"
	elif herd_target is not None and herd_target > 0:
		expected, source = herd_target, "herd target"
	else:
		expected, source = (min_adg + max_adg) / 2, "settings"
	expected = max(expected, 0.0)
	return {"low": min(min_adg, expected), "expected": expected, "high": max(max_adg, expected), "source": source}


def daily_feed_kg(weight_kg, pct):
	return (weight_kg or 0) * pct / 100.0


def exit_day(kg, adg, exit_kg):
	"""Day (from today) the animal leaves; None when it never does."""
	if not exit_kg:
		return None
	if kg >= exit_kg:
		return WEEK
	if not adg or adg <= 0:
		return None
	return max(1, math.ceil(round((exit_kg - kg) / adg, 9)))


def band_of(weight_kg, bands):
	for b in bands or []:
		if weight_kg >= b["min_kg"] and (b["max_kg"] is None or weight_kg < b["max_kg"]):
			return b["herd"]
	return None


def days_at_rate(stock_kg, day_kg):
	if not day_kg or day_kg <= 0:
		return None
	return stock_kg / day_kg


def days_of_feed(stock_kg, weeks):
	"""Days until `stock_kg` is used up, walking the weekly need; None if it outlasts the horizon
	(or nothing is eaten)."""
	if not any(w["feed_kg"] > 0 for w in weeks):
		return None
	left = stock_kg
	for i, w in enumerate(weeks):
		need = w["feed_kg"]
		if need <= 0:
			continue
		if left < need:
			return i * WEEK + WEEK * left / need
		left -= need
	return None


def split_stock(central_kg, need_by_herd, own_by_herd):
	"""Each herd's stock: what sits in its own paddock plus a share of the central stores in
	proportion to its daily need."""
	total = sum(need_by_herd.values())
	out = {}
	for herd, need in need_by_herd.items():
		share = central_kg * need / total if total > 0 else 0.0
		out[herd] = float(own_by_herd.get(herd, 0.0)) + share
	return out


def _scenario(animals, weeks, pct, key, bands):
	"""Weekly rows per herd and in total for one scenario, plus band movement."""
	horizon = weeks * WEEK
	herds = {}
	band_state = []
	for a in animals:
		adg = a["adg"][key]
		kg = a["kg"]
		leave = exit_day(kg, adg, a.get("exit_kg"))
		herds.setdefault(a["herd"], []).append((kg, adg, leave, a))
	rows = {}
	for herd, items in herds.items():
		rows[herd] = [_week_row(items, i, pct) for i in range(weeks)]
	total = [_merge([rows[h][i] for h in rows], i) for i in range(weeks)]
	for r in (total, *rows.values()):
		cum = 0.0
		for w in r:
			cum += w["feed_kg"]
			w["cumulative_kg"] = cum
	if bands and key == "expected":
		band_state = _bands(animals, weeks, bands, key)
	return rows, total, band_state, horizon


def _week_row(items, i, pct):
	d0, d1 = i * WEEK, (i + 1) * WEEK
	feed = 0.0
	head = exits = 0
	live = 0.0
	for kg, adg, leave, _a in items:
		stay = WEEK if leave is None else max(0, min(leave - d0, WEEK))
		if stay > 0:
			feed += daily_feed_kg(kg + adg * (d0 + stay / 2.0), pct) * stay
		if leave is not None and d0 < leave <= d1:
			exits += 1
		if leave is None or leave > d1:
			head += 1
			live += kg + adg * d1
	return {"week": i + 1, "feed_kg": feed, "head": head, "exits": exits, "live_kg": live,
	        "avg_kg": (live / head) if head else None}


def _merge(rows, i):
	head = sum(r["head"] for r in rows)
	live = sum(r["live_kg"] for r in rows)
	return {"week": i + 1, "feed_kg": sum(r["feed_kg"] for r in rows), "head": head,
	        "exits": sum(r["exits"] for r in rows), "live_kg": live, "avg_kg": (live / head) if head else None}


def _bands(animals, weeks, bands, key):
	names = [b["herd"] for b in bands]
	today = {n: 0 for n in names}
	grown = [a for a in animals if a["herd"] in names]
	for a in grown:
		b = band_of(a["kg"], bands)
		if b:
			today[b] += 1
	out = []
	for i in range(weeks):
		d0, d1 = i * WEEK, (i + 1) * WEEK
		counts = {n: 0 for n in names}
		moves = {}
		exits = 0
		for a in grown:
			adg = a["adg"][key]
			leave = exit_day(a["kg"], adg, a.get("exit_kg"))
			if leave is not None and leave <= d0:
				continue
			before = band_of(a["kg"] + adg * d0, bands)
			if leave is not None and leave <= d1:
				exits += 1
				continue
			after = band_of(a["kg"] + adg * d1, bands)
			if after:
				counts[after] += 1
			if before and after and before != after:
				moves[(before, after)] = moves.get((before, after), 0) + 1
		order = {n: k for k, n in enumerate(names)}
		out.append({
			"week": i + 1, "counts": counts, "exits": exits,
			"moves": [{"from": f, "to": t, "head": n}
			          for (f, t), n in sorted(moves.items(), key=lambda kv: (order[kv[0][0]], order[kv[0][1]]))],
		})
	return {"today": today, "weeks": out}


def project(animals, weeks, pct, bands=None):
	"""The whole projection.

	`animals`: [{id, herd, kg (today), adg {low, expected, high}, exit_kg|None}].
	`bands`: the feedlot ladder [{herd, min_kg, max_kg|None}]; only animals now in one of its herds move along it.
	Returns {"herds": {herd: {head, live_kg, day_kg, low|expected|high: {weeks}}},
	         "total": {same}, "bands": {today, weeks}|None}.
	"""
	by_herd = {}
	for a in animals:
		by_herd.setdefault(a["herd"], []).append(a)

	def today(items):
		live = sum(a["kg"] for a in items)
		return {"head": len(items), "live_kg": live, "day_kg": daily_feed_kg(live, pct)}

	out = {"herds": {h: today(items) for h, items in by_herd.items()}, "total": today(animals), "bands": None}
	for h in out["herds"]:
		out["herds"][h].update({sc: {"weeks": []} for sc in SCENARIOS})
	out["total"].update({sc: {"weeks": []} for sc in SCENARIOS})
	band_block = None
	for sc in SCENARIOS:
		rows, total, band_state, _ = _scenario(animals, weeks, pct, sc, bands if sc == "expected" else None)
		for h, r in rows.items():
			out["herds"][h][sc]["weeks"] = r
		out["total"][sc]["weeks"] = total
		if sc == "expected" and band_state:
			band_block = band_state
	out["bands"] = band_block
	return out
