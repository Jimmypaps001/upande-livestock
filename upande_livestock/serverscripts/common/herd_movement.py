# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where an animal belongs, and when it should move.

Two rules shape everything here.

DAYS COME FROM SETTINGS, NEVER FROM A HERD'S NAME. "2-4" and "4-12 MONTHS
(WEANERS)" read like rules but they are labels somebody chose; a farm that
renames a herd must not silently change how long its animals stay in it.

The growth ladder is ordered and time-driven, and ends the moment a heifer is old
enough to serve. Past that point movement is driven by breeding events.
"""

import frappe
from frappe.utils import add_days, date_diff, getdate, today

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.timings import get_timing

SETTINGS = "Livestock Settings"


def settings():
	return frappe.get_cached_doc(SETTINGS)


# ---------------------------------------------------------------------------
# the growth ladder
# ---------------------------------------------------------------------------


def growth_ladder():
	"""The rungs in order. Row order IS the movement order."""
	return [
		{
			"idx": r.idx,
			"herd": r.herd,
			"days_in_herd": int(r.days_in_herd or 0),
			"max_days_in_herd": int(r.max_days_in_herd or 0),
			"exits_on_service": bool(r.exits_on_service),
		}
		for r in (settings().get("growth_ladder") or [])
		if r.herd
	]


def ladder_position(herd):
	"""Which rung a herd is, or None if it is not on the ladder at all."""
	for i, rung in enumerate(growth_ladder()):
		if rung["herd"] == herd:
			return i
	return None


def next_growth_herd(herd):
	"""The rung after this one, or None at the top of the ladder."""
	rungs = growth_ladder()
	i = ladder_position(herd)
	if i is None or i + 1 >= len(rungs):
		return None
	return rungs[i + 1]["herd"]


def cow_herd():
	"""Where a cow goes when she calves: Livestock Settings' cow herd, if it names a herd."""
	herd = settings().get("cow_herd")
	return herd if herd and frappe.db.exists("Herds", herd) else None


def calving_destinations(dam):
	"""Where the dam and each kind of calf stand once this calving is recorded.

	Answered before anything is written, so the person at the pen can see it and
	stop if it is wrong. Sex decides the calves and nothing else does; the dam
	goes to the cow herd if Settings names one, otherwise stays where she is.
	"""
	row = frappe.db.get_value("Animal", dam, ["current_herd", "burn_name", "sex"], as_dict=True) \
		if dam else None
	from_herd = row.current_herd if row else None
	to_herd = cow_herd() or from_herd

	return {
		"dam": {
			"animal": dam,
			"label": (row.burn_name if row else None) or dam,
			"from_herd": from_herd,
			"to_herd": to_herd,
			"will_move": bool(to_herd and from_herd != to_herd),
			"reason": "she moves to the cow herd" if to_herd and from_herd != to_herd
			          else "a cow stays in her herd with her calf",
		},
		"female_calf": {
			"to_herd": calf_herd("Female"),
			"reason": "a heifer calf joins the growth ladder",
		},
		"male_calf": {
			"to_herd": calf_herd("Male"),
			"reason": "a bull calf goes to the bull herd",
		},
	}


def calf_herd(sex):
	"""Where a newborn goes. Sex decides this and nothing else does."""
	s = settings()
	if (sex or "").strip().lower().startswith("m"):
		return s.get("male_calf_herd")
	return s.get("female_calf_herd")


# ---------------------------------------------------------------------------
# how long an animal has been where it is
# ---------------------------------------------------------------------------


def days_in_current_herd(animal):
	"""Days since the animal last arrived in its herd.

	Measured from the most recent Movement event into that herd, falling back to
	date of birth for an animal that has never moved — a calf in its first herd
	has no movement to measure from, and using its age is exactly right there.
	"""
	row = frappe.db.get_value("Animal", animal, ["current_herd", "date_of_birth"], as_dict=True)
	if not row:
		return None
	arrived = frappe.db.get_value(
		"Livestock Event",
		{"animal": animal, "event_type": "Movement", "new_herd": row.current_herd, "docstatus": 1},
		"event_date",
		order_by="event_date desc",
	)
	arrived = arrived or row.date_of_birth
	if not arrived:
		return None
	return date_diff(today(), getdate(arrived))


def growth_move_due(animal):
	"""Is this animal due to climb a rung? Returns a dict, or None when the
	question does not apply — it is not on the ladder, or the rung it sits on
	is the one you leave by being served rather than by waiting."""
	herd = frappe.db.get_value("Animal", animal, "current_herd")
	if not herd:
		return None
	i = ladder_position(herd)
	if i is None:
		return None
	rung = growth_ladder()[i]
	if rung["exits_on_service"]:
		return None

	days = days_in_current_herd(animal)
	if days is None:
		return None
	nxt = next_growth_herd(herd)
	limit = rung["days_in_herd"] or 0
	mx = rung["max_days_in_herd"] or 0
	return {
		"animal": animal,
		"herd": herd,
		"next_herd": nxt,
		"days_in_herd": days,
		"days_expected": limit,
		"due": bool(limit and days >= limit and nxt),
		"overdue": bool(mx and days > mx),
		"days_over": max(0, days - mx) if mx else 0,
	}


# ---------------------------------------------------------------------------
# eligibility — derived from where an animal stands, never set by hand
# ---------------------------------------------------------------------------


def heifer_herds():
	"""The herds that hold heifers: Livestock Settings' Heifer herds table.

	Empty when the farm has not filled it in; clients then fall back to
	stage and age, which also catches calves.
	"""
	s = settings()
	return list(dict.fromkeys(r.herd for r in (s.get("heifer_herds") or []) if r.herd))


def _settings_herds(table):
	s = settings()
	return list(dict.fromkeys(r.herd for r in (s.get(table) or []) if r.herd))


def in_calf_herds():
	"""Where in-calf animals go: Livestock Settings' In-calf herds table. Empty when unset."""
	return _settings_herds("in_calf_herds")


def calf_group_herds():
	"""The calf groups: Livestock Settings' Calf herds table. Empty when unset.

	Not calf_herd(sex), which is the single herd a newborn is put in.
	"""
	return _settings_herds("calf_herds")


def service_herds():
	"""The rungs of the ladder that are left by being served, plus the cow herd
	and every herd whose class is Cow.

	A heifer becomes servable at the top of the ladder; a cow becomes servable
	again once she is far enough past calving, which `service_wait_days` covers.
	"""
	herds = [r["herd"] for r in growth_ladder() if r["exits_on_service"]]
	cows = [cow_herd()] + frappe.get_all("Herds", filters={"herd_class": "Cow"}, pluck="name")
	return herds + [h for h in dict.fromkeys(cows) if h and h not in herds]


def service_wait_days():
	"""Days after calving before a cow is OFFERED for service again.

	The optimal window, not the minimum. Settings holds both: a hard floor
	(post_calving_min_service_days, 45 here) below which a service is refused,
	and the point the farm actually starts serving (60). Offering from the floor
	puts cows in front of the breeder three weeks before anybody would serve
	them; the floor stays where it is, guarding a deliberate override.
	"""
	return get_timing("post_calving_optimal_service_days") or get_timing("post_calving_min_service_days")


def is_servable(animal):
	"""In a herd that services happen from, and past the post-calving wait."""
	row = frappe.db.get_value(
		"Animal", animal, ["current_herd", "last_calving_date", "repro_status"], as_dict=True
	)
	if not row or row.current_herd not in service_herds():
		return False
	if row.last_calving_date:
		wait = service_wait_days()
		if wait and date_diff(today(), getdate(row.last_calving_date)) < wait:
			return False
	return True


def has_open_service(animal):
	"""Is there a submitted Service still awaiting its pregnancy check?

	A diagnosis answers a question a service asked. Without one there is nothing
	to diagnose, and recording a result would invent a pregnancy from nothing.
	"""
	return bool(frappe.db.exists("Livestock Event", {
		"animal": animal,
		"event_type": "Service",
		"docstatus": 1,
		"pregnancy_confirmation_status": "Pending",
	}))


def diagnosable_animals():
	"""Animals with an open service, newest service first.

	AND NOT ALREADY CHECKED TODAY. `guards.check_once_per_day` refuses a second
	submitted Pregnancy Diagnosis on one animal on one day, so a cow who has
	been checked this morning is a cow the screen would offer and the server
	would then refuse — after the herdsman has filled the form in. The list is
	narrowed by exactly what the guard enforces rather than by a second opinion
	about it.

	A cow whose check came back Confirmed drops off on her own: her service is
	no longer Pending. That only became true once the write-back was moved out
	of `before_insert`, where it never ran — see
	`patches.settle_services_their_diagnoses_answered`.
	"""
	rows = frappe.db.sql(
		"""SELECT s.animal, MAX(s.service_date) AS served, MAX(s.name) AS service
		   FROM `tabLivestock Event` s
		   JOIN `tabAnimal` a ON a.name = s.animal
		   WHERE s.event_type = 'Service' AND s.docstatus = 1
		     AND s.pregnancy_confirmation_status = 'Pending'
		     AND IFNULL(a.status, '') NOT IN ('Dead','Deceased','Sold','Culled','Disposed')
		     AND IFNULL(a.disabled, 0) = 0
		     AND NOT EXISTS (
		       SELECT 1 FROM `tabLivestock Event` d
		       WHERE d.animal = s.animal AND d.docstatus = 1
		         AND d.event_type = 'Pregnancy Diagnosis'
		         AND d.event_date = %(today)s)
		   GROUP BY s.animal
		   ORDER BY served DESC
		   LIMIT 2000""",
		{"today": today()},
		as_dict=True,
	)
	return rows


def carrying_animals():
	"""Cows the farm believes are in calf, newest confirmation first.

	A CONFIRMED pregnancy with no calving or abortion since. An abortion can
	only happen to an animal that was carrying one — offering the whole herd
	invites a loss recorded against a cow who was never pregnant, and there is
	then nothing for it to close and nothing that reads as a mistake afterwards.

	The same query drives the feed forecast's calving schedule, so a cow who is
	on this list is a cow the farm is buying feed for a calf for.
	"""
	return frappe.db.sql(
		"""SELECT s.animal, MAX(s.service_date) AS served, MAX(s.name) AS service
		   FROM `tabLivestock Event` s JOIN `tabAnimal` a ON a.name = s.animal
		   WHERE s.event_type = 'Service' AND s.docstatus = 1
		     AND s.pregnancy_confirmation_status = 'Confirmed'
		     AND IFNULL(a.disabled, 0) = 0
		     AND IFNULL(a.status, '') NOT IN ('Dead','Deceased','Sold','Culled','Disposed')
		     AND NOT EXISTS (
		         SELECT 1 FROM `tabLivestock Event` c
		         WHERE c.animal = s.animal AND c.docstatus = 1
		           AND c.event_type IN ('Calving', 'Abortion')
		           AND c.event_date >= s.service_date)
		   GROUP BY s.animal
		   ORDER BY served DESC
		   LIMIT 2000""",
		as_dict=True,
	)


def open_days(animal):
	"""Days since calving without a confirmed pregnancy, or None if not open."""
	row = frappe.db.get_value(
		"Animal", animal, ["last_calving_date", "repro_status"], as_dict=True
	)
	if not row or not row.last_calving_date:
		return None
	if (row.repro_status or "").strip().lower() in ("pregnant", "confirmed", "in calf"):
		return None
	return date_diff(today(), getdate(row.last_calving_date))


def open_too_long(animal):
	"""A cow that has not conceived within the farm's limit is open too long."""
	limit = get_timing("max_open_days")
	if not limit:
		return None
	days = open_days(animal)
	if days is None or days <= limit:
		return None
	return {"animal": animal, "open_days": days, "limit": limit, "days_over": days - limit}


# ---------------------------------------------------------------------------
# gestation
# ---------------------------------------------------------------------------


def expected_calving_date(conception_date):
	"""Conception plus gestation. Nine months, from settings."""
	days = get_timing("gestation_period_days")
	return add_days(getdate(conception_date), days) if conception_date else None


# ---------------------------------------------------------------------------
# suggestions — what the farm should do about all this
# ---------------------------------------------------------------------------


def _animals_in(herd):
	return frappe.get_all(
		"Animal",
		filters=[
			["current_herd", "=", herd],
			["status", "not in", ["Dead", "Deceased", "Sold", "Culled", "Disposed"]],
			["disabled", "=", 0],
		],
		fields=["name", "tag_number", "burn_name", "sex", "date_of_birth",
		        "last_calving_date", "repro_status", "current_herd"],
		limit=5000,
	)


def _label(a):
	return a.get("tag_number") or a.get("burn_name") or a.get("name")


def growth_suggestions():
	"""Heifers whose time on their rung is up.

	Males are skipped: bulls and steers do not climb the heifer ladder — their
	moves are driven by weight (see weight_bands). Only the growth ladder — everything past it moves on breeding events, which
	a day count cannot predict.
	"""
	out = []
	for rung in growth_ladder():
		if rung["exits_on_service"]:
			continue
		nxt = next_growth_herd(rung["herd"])
		if not nxt:
			continue
		for a in _animals_in(rung["herd"]):
			if (a.get("sex") or "").strip().lower().startswith("m"):
				continue
			state = growth_move_due(a["name"])
			if not state or not (state["due"] or state["overdue"]):
				continue
			out.append({
				"animal": a["name"],
				"label": _label(a),
				"from_herd": rung["herd"],
				"to_herd": nxt,
				"days_in_herd": state["days_in_herd"],
				"days_expected": state["days_expected"],
				"overdue": state["overdue"],
				"days_over": state["days_over"],
				"reason": "overdue by {} day(s)".format(state["days_over"])
				if state["overdue"] else "due — {} of {} days".format(
					state["days_in_herd"], state["days_expected"]),
			})
	out.sort(key=lambda r: (not r["overdue"], -r["days_in_herd"]))
	return out


def open_cow_warnings():
	"""Cows that have gone too long without conceiving."""
	limit = get_timing("max_open_days")
	if not limit:
		return []
	out = []
	for herd in service_herds():
		for a in _animals_in(herd):
			st = open_too_long(a["name"])
			if not st:
				continue
			out.append({
				"animal": a["name"],
				"label": _label(a),
				"herd": herd,
				"open_days": st["open_days"],
				"limit": st["limit"],
				"days_over": st["days_over"],
				"reason": "{} days open, {} past the {}-day limit".format(
					st["open_days"], st["days_over"], st["limit"]),
			})
	out.sort(key=lambda r: -r["open_days"])
	return out


def conception_date(animal):
	"""The service her confirmed pregnancy answers, or None if she is not carrying.

	The SERVICE date, not the date of the diagnosis: a cow scanned at 45 days
	conceived 45 days before somebody looked at her, and counting from the scan
	would put her calving date six weeks late.
	"""
	row = frappe.db.sql(
		"""SELECT s.service_date
		   FROM `tabLivestock Event` s
		   WHERE s.animal = %s AND s.event_type = 'Service' AND s.docstatus = 1
		     AND s.pregnancy_confirmation_status = 'Confirmed'
		     AND NOT EXISTS (
		         SELECT 1 FROM `tabLivestock Event` c
		         WHERE c.animal = s.animal AND c.event_type = 'Calving'
		           AND c.docstatus = 1 AND c.event_date >= s.service_date)
		   ORDER BY s.service_date DESC LIMIT 1""",
		(animal,),
	)
	return getdate(row[0][0]) if row and row[0][0] else None


def suggestions():
	"""Everything the farm should look at, in one call."""
	growth = growth_suggestions()
	open_cows = open_cow_warnings()
	return {
		"growth": growth,
		"open_cows": open_cows,
		"counts": {
			"growth": len(growth),
			"growth_overdue": sum(1 for r in growth if r["overdue"]),
			"open_cows": len(open_cows),
		},
	}


# ---------------------------------------------------------------------------
# who each breeding screen may offer
#
# EVERY LIST HERE IS A NARROWING, and every threshold in it comes from Livestock
# Settings rather than from a number typed into this file. The farm moves its
# gestation length or its calving alert lead on the Settings page and these lists
# move with it; a 60 written in here would be a second, disagreeing copy of the
# farm's own rule, which is exactly how api/reproduction.py came to answer 8
# animals ready where this package answered 2.
#
# The point of narrowing is not tidiness. An event recorded against an animal it
# cannot biologically have happened to does not stay a bad row: a calving
# creates a calf, a confirmed pregnancy drives the feed forecast for months. The
# cheapest place to prevent all of that is the list the screen offers.
# ---------------------------------------------------------------------------


def _carrying_rows():
	"""Carrying cows with the date they conceived, keyed by animal."""
	return {r["animal"]: r for r in carrying_animals()}


def calving_candidates():
	"""Cows about to calve: carrying, and near their date.

	The window is the gestation length plus the farm's calving alert lead, both
	from Settings. A cow past her date is still here, and first: overdue is the
	one state on this list that needs somebody to look at her today.
	"""
	lead = get_timing("calving_alert_lead_days")
	out = []
	for animal, row in _carrying_rows().items():
		conceived = conception_date(animal) or row.get("served")
		due = expected_calving_date(conceived)
		if not due:
			continue
		days_to_calving = date_diff(getdate(due), getdate(today()))
		out.append({
			"animal": animal,
			"herd": frappe.db.get_value("Animal", animal, "current_herd"),
			"due": str(due),
			"days_to_calving": days_to_calving,
			# Ready to calve, by the farm's own lead time. Never a refusal —
			# calves arrive early, and a screen that refused to record one would
			# send the herdsman to the desk to do it anyway.
			"ready": days_to_calving <= max(lead, 0),
		})
	out.sort(key=lambda r: r["days_to_calving"])
	return out


def service_age_months():
	"""How old a heifer must be before anybody serves her. From Settings."""
	return get_timing("min_service_age_months")


def heat_candidates():
	"""Cows worth recording a heat on: old enough, and not already in calf.

	TWO KINDS OF ANIMAL, and the second is the one the old list lost. A maiden
	heifer of age is obviously here. So is a cow served three weeks ago whose
	service is still pending — because her coming back into heat IS the answer
	to that service, and it is the farm finding out the insemination failed
	weeks before the pregnancy check would have said so. The old screen offered
	only the servable list, which excludes her the moment she is served.

	A confirmed pregnancy takes her off: a cow in calf showing standing heat is
	a diagnosis to revisit, not a heat to record against her pregnancy.
	"""
	months = service_age_months()
	carrying = set(_carrying_rows())
	rows = frappe.db.sql(
		"""SELECT a.name, a.tag_number, a.burn_name, a.current_herd, a.sex,
		          a.date_of_birth, a.last_calving_date
		   FROM `tabAnimal` a
		   WHERE IFNULL(a.status,'') NOT IN %(retired)s
		     AND IFNULL(a.disabled, 0) = 0
		     AND IFNULL(a.sex, '') = 'Female'
		   ORDER BY a.tag_number ASC
		   LIMIT 2000""",
		{"retired": tuple(RETIRED_STATUSES)},
		as_dict=True,
	)
	out = []
	for a in rows:
		if a.name in carrying:
			continue
		if months and a.date_of_birth:
			if date_diff(getdate(today()), getdate(a.date_of_birth)) < months * 30:
				continue
		elif months and not a.date_of_birth:
			# No birthday on file. She is not excluded on a guess — an animal
			# with no date of birth is a record to fix, not a cow to hide.
			pass
		out.append({
			"animal": a.name,
			"herd": a.current_herd,
			# A pending service means this heat is the answer to it.
			"repeat": has_open_service(a.name),
		})
	return out
