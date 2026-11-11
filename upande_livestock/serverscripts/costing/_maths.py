# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Cost per animal per day: the arithmetic, with no database in it.

The farm's figure is the one on its own spreadsheet's "Daily Totals" sheet:
feed + labour + fuel + medicine for the day, divided over every animal on the
farm that day. Everything here takes plain values and returns plain values, so
the rules can be tested without a site and the endpoint (`cost_per_animal`) is
left with nothing to do but read the ledger and call these.

The rules, as agreed with the farm on 2026-11-11:

* **Labour, fuel and medicine are spread evenly** over every animal on the farm
  that day, by-number shoats included. Nobody records which herd a worker or a
  tractor spent the morning on, so splitting them by herd would be invention.
* **Feed stays per herd.** Every feed issue names the herd it went to, so the
  herd figure is a real one: feed cost that day ÷ the herd's head that day.
* **A day with no animals has no cost per animal**, not a zero and not an
  infinity. `None` travels to the page, which shows a dash.

Money is rounded once, at the edge (`money`), never in the middle of a sum —
a month built from thirty pre-rounded days drifts from the ledger by cents
nobody can explain.
"""

import re
from datetime import date, timedelta

#: The labour categories, in the farm's words and in the order the screen
#: shows them. Mirrors the Select on Livestock Daily Labour Entry.
LABOUR_CATEGORIES = ("Feedlot workers", "Herders", "Other")

#: Livestock Settings field holding each category's default day rate.
RATE_FIELDS = {
	"Feedlot workers": "labour_rate_feedlot_workers",
	"Herders": "labour_rate_herders",
	"Other": "labour_rate_other",
}

#: How a feed issue to a herd is remarked (`feeding/_engine._post_feed_issue`).
FEED_PREFIX = "Animal feeding - "
#: A run posted after the day it was eaten carries that day in its remark.
_FED_ON = re.compile(r" - fed (\d{4}-\d{2}-\d{2})")

#: The cost kinds, in the order the page shows them.
KINDS = ("feed_cost", "medicine_cost", "labour_cost", "fuel_cost")


def money(x) -> float:
	return round(float(x or 0), 2)


def as_date(value) -> date:
	if isinstance(value, date):
		return value
	return date.fromisoformat(str(value)[:10])


def days_between(lo, hi):
	"""Every day from `lo` to `hi`, both included. Empty when `hi` is before `lo`."""
	lo, hi = as_date(lo), as_date(hi)
	return [lo + timedelta(days=i) for i in range((hi - lo).days + 1)]


# ---------------------------------------------------------------------------
# labour
# ---------------------------------------------------------------------------


def labour_lines(rows, default_rates):
	"""Clean a day's labour rows: fill the rate from the defaults, work out the amount.

	A row with no rate (blank or 0) takes its category's default (Livestock
	Settings), so the manager types only the number of workers on an ordinary
	day. A rate typed on the row wins: a day the herders were paid overtime is
	still that day's cost.
	Rows with no workers are dropped rather than stored as zero lines.

	Raises ValueError, in the farm's words, on an unknown category or a
	negative number; the caller turns it into the page's error.
	"""
	out = []
	for row in rows or []:
		category = (row.get("category") or "").strip()
		if category not in LABOUR_CATEGORIES:
			raise ValueError(f"Unknown labour category: {category or '(blank)'}.")
		workers = int(float(row.get("workers") or 0))
		if workers < 0:
			raise ValueError(f"{category}: the number of workers cannot be negative.")
		if workers == 0:
			continue
		# Blank and 0 both mean "the usual rate": nobody works the feedlot for
		# nothing, and the desk grid shows an untouched Currency cell as 0.
		rate = float(row.get("day_rate") or 0) or float(default_rates.get(category) or 0)
		if rate < 0:
			raise ValueError(f"{category}: the day rate cannot be negative.")
		out.append({
			"category": category,
			"workers": workers,
			"day_rate": money(rate),
			"amount": money(workers * rate),
			"notes": (row.get("notes") or "").strip(),
		})
	return out


# ---------------------------------------------------------------------------
# who was on the farm
# ---------------------------------------------------------------------------


def count_present(days, stays):
	"""{day: how many stays cover it}. A stay is (from, to): `from` counts, `to` does not.

	`to` None means still there. Built as a running sum of arrivals and
	departures rather than by testing every stay against every day, so a
	year's report over a few thousand animals is one pass, not millions.
	"""
	days = list(days)
	if not days:
		return {}
	lo, hi = days[0], days[-1]
	delta = {}
	for start, end in stays:
		start = as_date(start)
		end = as_date(end) if end else None
		if end is not None and end <= start:
			continue
		if start > hi or (end is not None and end <= lo):
			continue
		first = max(start, lo)
		delta[first] = delta.get(first, 0) + 1
		if end is not None and end <= hi:
			delta[end] = delta.get(end, 0) - 1
	out, running = {}, 0
	for day in days:
		running += delta.get(day, 0)
		out[day] = running
	return out


def clip_stay(start, end, exit_day):
	"""A stay cut short by the animal leaving the farm on `exit_day` (that day not counted)."""
	if exit_day is None:
		return (start, end)
	exit_day = as_date(exit_day)
	if end is None or as_date(end) > exit_day:
		end = exit_day
	return (start, end)


def replay_heads(days, events, apply, zero, total):
	"""{day: head} for a by-number herd, from its count events.

	`events` are already in ledger order (`common.shoats.submitted`); `apply`,
	`zero` and `total` are that module's, passed in so this stays free of the
	database. The head on a day is after every event dated that day or before.
	"""
	days = list(days)
	state = zero()
	out = {}
	i = 0
	events = list(events)
	for day in days:
		while i < len(events) and as_date(events[i]["event_date"]) <= day:
			state = apply(state, events[i])
			i += 1
		out[day] = max(total(state), 0)
	return out


# ---------------------------------------------------------------------------
# reading the ledger's remarks
# ---------------------------------------------------------------------------


def herd_of_feed(remarks, herds):
	"""Which herd a feed issue went to, from its remark, or None.

	The longest herd name that fits wins, so herd "Group 1" does not claim
	herd "Group 1 - Finishers"'s feed; and the name must be followed by the
	remark's own separator, so herd "0-2" does not claim "10-2"'s.
	"""
	text = remarks or ""
	if not text.startswith(FEED_PREFIX):
		return None
	rest = text[len(FEED_PREFIX):]
	best = None
	for herd in herds:
		if rest.startswith(f"{herd} - ") and (best is None or len(herd) > len(best)):
			best = herd
	return best


def fed_day(remarks, posting_date):
	"""The day the feed was eaten: the remark's "- fed <day>" if any, else the posting date."""
	m = _FED_ON.search(remarks or "")
	return as_date(m.group(1)) if m else as_date(posting_date)


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------


def per_animal(cost, animals):
	return money(cost / animals) if animals else None


def build_report(days, feed, medicine, labour, fuel, animals, herd_feed, herd_heads):
	"""Assemble the day rows, the month totals and the per-herd feed figures.

	`feed`, `medicine`, `labour`, `fuel` and `animals` are {day: value};
	`herd_feed` is {herd: {day: cost}} and `herd_heads` {herd: {day: head}}.
	A day missing from any of them is a zero for it.
	"""
	days = list(days)
	rows = []
	for day in days:
		row = {
			"date": day.isoformat(),
			"feed_cost": float(feed.get(day, 0) or 0),
			"medicine_cost": float(medicine.get(day, 0) or 0),
			"labour_cost": float(labour.get(day, 0) or 0),
			"fuel_cost": float(fuel.get(day, 0) or 0),
			"animals": int(animals.get(day, 0) or 0),
		}
		row["total_cost"] = sum(row[k] for k in KINDS)
		row["cost_per_animal"] = per_animal(row["total_cost"], row["animals"])
		rows.append(row)

	months = {}
	for row in rows:
		m = months.setdefault(row["date"][:7], {"month": row["date"][:7], "days": 0, "animal_days": 0,
		                                         **{k: 0.0 for k in KINDS}, "total_cost": 0.0})
		m["days"] += 1
		m["animal_days"] += row["animals"]
		for k in (*KINDS, "total_cost"):
			m[k] += row[k]
	month_rows = []
	for m in months.values():
		# Per animal per day over the month: what the month cost, over the animal-days it carried.
		m["cost_per_animal"] = per_animal(m["total_cost"], m["animal_days"])
		m["average_animals"] = round(m["animal_days"] / m["days"], 1) if m["days"] else 0
		month_rows.append(_rounded(m))

	in_window = set(days)
	herds = []
	for herd in sorted(set(herd_feed) | set(herd_heads)):
		cost_by_day = herd_feed.get(herd, {})
		heads_by_day = herd_heads.get(herd, {})
		herd_days = []
		for day in days:
			cost = float(cost_by_day.get(day, 0) or 0)
			heads = int(heads_by_day.get(day, 0) or 0)
			if cost or heads:
				herd_days.append({"date": day.isoformat(), "feed_cost": money(cost), "heads": heads,
				                  "feed_cost_per_head": per_animal(cost, heads)})
		cost = sum(float(v or 0) for d, v in cost_by_day.items() if d in in_window)
		head_days = sum(int(heads_by_day.get(d, 0) or 0) for d in days)
		if not cost and not head_days:
			continue
		herds.append({
			"herd": herd,
			"feed_cost": money(cost),
			"head_days": head_days,
			"average_heads": round(head_days / len(days), 1) if days else 0,
			# Over the head-days, not the days: a herd that grew mid-month is
			# charged for the animals it actually fed.
			"feed_cost_per_head_day": per_animal(cost, head_days),
			"days": herd_days,
		})

	total = {"days": len(rows), "animal_days": sum(r["animals"] for r in rows),
	         **{k: sum(r[k] for r in rows) for k in KINDS}}
	total["total_cost"] = sum(total[k] for k in KINDS)
	total["cost_per_animal"] = per_animal(total["total_cost"], total["animal_days"])
	return {"days": [_rounded(r) for r in rows], "months": month_rows, "herds": herds, "total": _rounded(total)}


def _rounded(row):
	return {k: money(v) if k in (*KINDS, "total_cost") else v for k, v in row.items()}
