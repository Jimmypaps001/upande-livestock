# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which cows the figures argue against keeping, and the figures themselves."""

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, today

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run

#: How far back the yearly bars go. Five is a cow's working life on this farm;
#: further back is a different animal in the same skin.
YEARS = 5

#: What counts as a long time to be open. 120 days past calving with nothing
#: holding is roughly one lost lactation a year, which is the number a manager
#: actually feels.
OPEN_DAYS_CONCERN = 120

#: Served this many times since she last held, and she is being paid for
#: without answering.
REPEAT_SERVICES = 3

#: Days ill in the last year before it is worth saying out loud.
SICK_DAYS_CONCERN = 21


@frappe.whitelist()
def cull_candidates(payload=None):
	"""Rank the herd by the case against each cow, worst first.

	A SUGGESTION, NEVER A DECISION. Everything here is read off records that
	already exist — services that did not hold, pregnancies lost, days under
	treatment, the interval between her calvings. No cow is culled by arithmetic
	and none is protected by it either: the list exists so the four or five
	worth looking at are not buried under four hundred that are fine, and the
	screen lets a manager raise a case against any animal at all.

	WHY EACH ONE IS HERE IS THE POINT. A ranked list with no reasons is an
	oracle, and nobody signs a disposal on an oracle's say-so. Every candidate
	carries the reasons that put her there, her own figures beside the herd's,
	and her last five years, so the argument can be read rather than trusted.

	PER-ANIMAL MILK IS NOT RECORDED ON THIS FARM — Milk Recording is per herd
	per session — so "low produce" cannot mean litres. It means what the records
	can actually support: the milk a health case cost her where somebody wrote
	it down, and the interval between her calvings, which is the farm's real
	measure of how much lactation it got out of her.
	"""

	def go():
		guard_read("Animal")
		d = as_dict(payload) if payload else {}
		want = int(d.get("limit") or 25)

		animals = frappe.get_all(
			"Animal",
			filters=[
				["status", "not in", list(RETIRED_STATUSES)],
				["disabled", "=", 0],
				["sex", "=", "Female"],
			],
			fields=["name", "burn_name", "tag_number", "current_herd", "date_of_birth",
			        "status", "last_calving_date", "repro_status"],
			limit_page_length=0,
		)
		if not animals:
			return {"ok": True, "candidates": [], "considered": 0, "herd": {}}

		facts = _facts([a.name for a in animals])
		herd = _medians(animals, facts)

		out = []
		for a in animals:
			f = facts.get(a.name, _blank())
			open_days = _open_days(a, f)
			reasons = _reasons(a, f, open_days)
			if not reasons:
				continue
			out.append({
				"animal": a.name,
				"name": a.tag_number or a.burn_name or a.name,
				"herd": a.current_herd,
				"status": a.status,
				"age_days": date_diff(today(), getdate(a.date_of_birth)) if a.date_of_birth else None,
				"score": sum(r["weight"] for r in reasons),
				"reasons": reasons,
				"bars": _bars(f, herd, open_days),
				"years": _years(f),
			})

		out.sort(key=lambda r: (-r["score"], r["name"]))
		return {
			"ok": True,
			"candidates": out[:want],
			"considered": len(animals),
			"flagged_count": len(out),
			"herd": herd,
			# Said in the payload so the screen does not have to know the farm's
			# recording habits to caption its own chart honestly.
			"per_animal_milk": False,
		}

	return run(go, "livestock cull_candidates failed")


def _blank():
	return {
		"calvings": [], "abortions": [], "services": [], "conceptions": [],
		"sick_days": 0.0, "sick_days_year": 0.0, "sick_by_year": {}, "cases": 0, "lost_kg": 0.0,
		"last_conception": None,
	}


def _facts(names):
	"""Everything the ranking needs, in four passes over the whole herd.

	Per animal it would be four hundred round trips for a page nobody waits
	for, so the queries are grouped and the arithmetic is done here.
	"""
	facts = {n: _blank() for n in names}
	year_ago = add_days(today(), -365)

	for row in frappe.db.sql(
		"""SELECT animal, event_type, event_date, pregnancy_confirmation_status
		   FROM `tabLivestock Event`
		   WHERE docstatus = 1
		     AND event_type IN ('Calving', 'Abortion', 'Service')
		     AND event_date IS NOT NULL""",
		as_dict=True,
	):
		f = facts.get(row.animal)
		if not f:
			continue
		on = getdate(row.event_date)
		if row.event_type == "Calving":
			f["calvings"].append(on)
		elif row.event_type == "Abortion":
			f["abortions"].append(on)
		else:
			f["services"].append(on)
			if (row.pregnancy_confirmation_status or "") == "Confirmed":
				f["conceptions"].append(on)

	for row in frappe.db.sql(
		"""SELECT animal, opened_date, closed_date, case_status,
		          duration_days, production_loss_kg
		   FROM `tabLivestock Health Case`
		   WHERE docstatus < 2 AND opened_date IS NOT NULL""",
		as_dict=True,
	):
		f = facts.get(row.animal)
		if not f:
			continue
		opened = getdate(row.opened_date)
		# An open case is still costing days. Taking duration_days at face value
		# would report a cow who has been under treatment for six weeks as
		# having been ill for none, because nobody closes a case that is not
		# over.
		if row.duration_days:
			days = flt(row.duration_days)
		elif row.closed_date:
			days = date_diff(getdate(row.closed_date), opened)
		else:
			days = date_diff(today(), opened)
		days = max(days, 0.0)
		f["cases"] += 1
		f["sick_days"] += days
		f["sick_by_year"][opened.year] = f["sick_by_year"].get(opened.year, 0.0) + days
		if opened >= getdate(year_ago):
			f["sick_days_year"] += days
		f["lost_kg"] += flt(row.production_loss_kg)

	for f in facts.values():
		f["calvings"].sort()
		f["abortions"].sort()
		f["services"].sort()
		f["conceptions"].sort()
		f["last_conception"] = f["conceptions"][-1] if f["conceptions"] else None

	return facts


def _interval(calvings):
	"""Her average calving interval in days, or None if she has calved once."""
	if len(calvings) < 2:
		return None
	# A zero or negative gap is two calvings entered on one day by the register
	# load, not a cow who calved twice in a morning. Counting them would drag
	# the herd median to nothing and make every real interval look terrible.
	gaps = [date_diff(b, a) for a, b in zip(calvings, calvings[1:]) if date_diff(b, a) > 0]
	if not gaps:
		return None
	return round(sum(gaps) / len(gaps))


def _open_days(animal, facts):
	"""Days since she last calved with nothing holding since."""
	last = facts["calvings"][-1] if facts["calvings"] else None
	if not last:
		return None
	if (animal.repro_status or "").strip().lower() in ("pregnant", "confirmed", "in calf"):
		return None
	if facts["last_conception"] and facts["last_conception"] > last:
		return None
	return date_diff(today(), last)


def _services_since(facts):
	"""Services since she last held — the ones the farm paid for and got nothing."""
	# The LATER of the two. A cow who conceived and then calved has answered
	# for every service up to the calving; counting from the conception would
	# hold three-year-old failures against her forever.
	marks = [d for d in (facts["last_conception"],
	                     facts["calvings"][-1] if facts["calvings"] else None) if d]
	since = max(marks) if marks else None
	if since:
		return sum(1 for s in facts["services"] if s > since)
	return len(facts["services"])


def _median(values):
	rows = sorted(v for v in values if v is not None)
	if not rows:
		return None
	mid = len(rows) // 2
	return rows[mid] if len(rows) % 2 else (rows[mid - 1] + rows[mid]) / 2.0


def _medians(animals, facts):
	"""The herd she is being measured against, over the cows that have each measure.

	Median, not mean: one nine-calving matriarch drags a mean far enough that
	half the herd reads as below it, which is precisely the comparison this
	exists to make honest.
	"""
	intervals, opens, sick = [], [], []
	for a in animals:
		f = facts.get(a.name, _blank())
		intervals.append(_interval(f["calvings"]))
		opens.append(_open_days(a, f))
		sick.append(f["sick_days_year"])
	return {
		"calving_interval": _median(intervals),
		"open_days": _median(opens),
		"sick_days": _median(sick),
	}


def _reasons(animal, facts, open_days):
	"""The case against her, in as many sentences as there are facts for.

	Each carries its own weight so the ranking can be read off the reasons
	rather than off a number nobody can take apart.
	"""
	out = []
	interval = _interval(facts["calvings"])
	repeats = _services_since(facts)
	losses = len(facts["abortions"])

	if losses >= 2:
		out.append({
			"key": "abortions",
			"label": f"{losses} pregnancies lost",
			"detail": "The last on " + str(facts["abortions"][-1]) + ".",
			"weight": 25 + 10 * (losses - 2),
		})
	elif losses == 1 and facts["abortions"][-1] >= getdate(add_days(today(), -365)):
		out.append({
			"key": "abortions",
			"label": "Lost a pregnancy this year",
			"detail": "On " + str(facts["abortions"][-1]) + ".",
			"weight": 10,
		})

	if repeats >= REPEAT_SERVICES:
		out.append({
			"key": "not_holding",
			"label": f"Served {repeats} times without holding",
			"detail": "Since she last conceived." if facts["last_conception"]
			          else "She has never held.",
			"weight": 15 + 5 * (repeats - REPEAT_SERVICES),
		})

	if open_days is not None and open_days > OPEN_DAYS_CONCERN:
		out.append({
			"key": "open",
			"label": f"{open_days} days open",
			"detail": f"Calved {facts['calvings'][-1]} and nothing has held since.",
			"weight": min(40, (open_days - OPEN_DAYS_CONCERN) // 30 * 8 + 8),
		})

	if facts["sick_days_year"] >= SICK_DAYS_CONCERN:
		out.append({
			"key": "sick",
			"label": f"{int(facts['sick_days_year'])} days ill this year",
			"detail": f"Across {facts['cases']} health case"
			          f"{'' if facts['cases'] == 1 else 's'}.",
			"weight": min(35, int(facts["sick_days_year"]) // 10 * 6),
		})

	if interval and interval > 450:
		out.append({
			"key": "interval",
			"label": f"{interval} days between calvings",
			"detail": "A year and a quarter of feed for one lactation.",
			"weight": min(30, (interval - 450) // 30 * 5 + 5),
		})

	if facts["lost_kg"] > 0:
		out.append({
			"key": "produce",
			"label": f"{int(facts['lost_kg'])} kg of milk lost to illness",
			"detail": "Recorded against her health cases.",
			"weight": min(20, int(facts["lost_kg"]) // 100 * 4 + 4),
		})

	return out


def _bars(facts, herd, open_days):
	"""Her figures beside the herd's, for the chart. Higher is worse on all three."""
	out = []
	for key, label, hers, unit in (
		("calving_interval", "Calving interval", _interval(facts["calvings"]), "d"),
		("open_days", "Days open", open_days, "d"),
		("sick_days", "Days ill this year", facts["sick_days_year"], "d"),
	):
		theirs = herd.get(key)
		if hers is None or theirs is None:
			continue
		# Nought against nought is not a comparison, it is a blank bar taking up
		# the room the real ones need.
		if not flt(hers) and not flt(theirs):
			continue
		out.append({
			"label": label, "hers": round(flt(hers), 1), "herd": round(flt(theirs), 1),
			"unit": unit, "worse": flt(hers) > flt(theirs),
		})
	return out


def _years(facts):
	"""Her last five years, one row each — what happened and what it cost."""
	this_year = getdate(today()).year
	span = list(range(this_year - YEARS + 1, this_year + 1))
	rows = {
		y: {"year": y, "calvings": 0, "abortions": 0, "services": 0, "sick_days": 0}
		for y in span
	}
	for on in facts["calvings"]:
		if on.year in rows:
			rows[on.year]["calvings"] += 1
	for on in facts["abortions"]:
		if on.year in rows:
			rows[on.year]["abortions"] += 1
	for on in facts["services"]:
		if on.year in rows:
			rows[on.year]["services"] += 1
	for year, days in facts["sick_by_year"].items():
		if year in rows:
			rows[year]["sick_days"] = int(days)
	return [rows[y] for y in span]
