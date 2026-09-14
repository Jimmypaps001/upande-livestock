# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where an animal belongs, and when it should move.

Two rules shape everything here.

DAYS COME FROM SETTINGS, NEVER FROM A HERD'S NAME. "2-4" and "4-12 MONTHS
(WEANERS)" read like rules but they are labels somebody chose; a farm that
renames a herd must not silently change how long its animals stay in it.

A HERD'S DURATION CAN BELONG TO THE ROUTE RATHER THAN THE HERD. Steamers takes
two streams — a first-time heifer arriving from Incalf Heifers with three months
to calving, and a cow arriving from the low-yield herd with two. Same herd,
different dry period, so `days_in_herd` is asked of the journey, not the place.

The growth ladder is ordered and time-driven, and ends the moment a heifer is old
enough to serve. Past that point movement is driven by breeding events, which is
why the lactation cycle is expressed as settings rather than as more rungs.
"""

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, today

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES

SETTINGS = "Livestock Settings"


#: How far past the farm's own number counts as LATE rather than merely due.
#: The calf ladder carries a `max_days_in_herd` for this; the lactation
#: settings have one number each, so the grace is stated here instead of being
#: invented differently at each call site.
LACTATION_GRACE_DAYS = 7


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


def post_calving_herd():
	"""Where a cow goes the moment she calves.

	A fresh cow is a milking cow, so this is the high-yield herd unless the farm
	says otherwise. The explicit setting exists because "high yield" is this
	farm's arrangement, not a rule — a farm that sends fresh cows to a transition
	group for a fortnight needs somewhere to say so.
	"""
	s = settings()
	explicit = s.get("post_calving_herd")
	if explicit and frappe.db.exists("Herds", explicit):
		return explicit
	high = s.get("high_yield_herd")
	return high if high and frappe.db.exists("Herds", high) else None


def calving_destinations(dam):
	"""Where the dam and each kind of calf stand once this calving is recorded.

	Answered before anything is written, so the person at the pen can see it and
	stop if it is wrong. Sex decides the calves and nothing else does; the dam
	goes wherever a fresh cow goes.
	"""
	row = frappe.db.get_value("Animal", dam, ["current_herd", "burn_name", "sex"], as_dict=True) \
		if dam else None
	from_herd = row.current_herd if row else None
	to_herd = post_calving_herd()

	return {
		"dam": {
			"animal": dam,
			"label": (row.burn_name if row else None) or dam,
			"from_herd": from_herd,
			"to_herd": to_herd,
			"will_move": bool(to_herd and from_herd != to_herd),
			"reason": _dam_reason(from_herd, to_herd),
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


def _dam_reason(from_herd, to_herd):
	if not to_herd:
		return ("no herd is set for a cow that has just calved — "
		        "set High Yield Herd in Livestock Settings")
	if from_herd == to_herd:
		return "already in the herd a fresh cow belongs to"
	if not from_herd:
		return "joins the milking herd"
	return "a fresh cow is a milking cow"


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
# bull calves
# ---------------------------------------------------------------------------


def bull_cull_status(animal):
	"""How far through its selling window a bull calf is.

	None when the farm does not sell bull calves off, or the animal is not one.
	"""
	s = settings()
	if not s.get("cull_bulls_after_birth"):
		return None
	window = int(s.get("bull_cull_max_days") or 0)
	if window <= 0:
		return None
	row = frappe.db.get_value(
		"Animal", animal, ["sex", "current_herd", "date_of_birth", "status"], as_dict=True
	)
	if not row or not row.date_of_birth:
		return None
	if not (row.sex or "").strip().lower().startswith("m"):
		return None
	if row.current_herd != s.get("male_calf_herd"):
		return None

	days = date_diff(today(), getdate(row.date_of_birth))
	warn_at = window * flt(s.get("bull_cull_warn_percent") or 75) / 100.0
	return {
		"animal": animal,
		"herd": row.current_herd,
		"days_on_farm": days,
		"window_days": window,
		"warn_after_days": warn_at,
		"days_remaining": window - days,
		"warn": days >= warn_at,
		"overdue": days > window,
	}


# ---------------------------------------------------------------------------
# eligibility — derived from where an animal stands, never set by hand
# ---------------------------------------------------------------------------


def milking_herds():
	"""Only the lactation groups are ever in milk."""
	s = settings()
	return [h for h in (s.get("high_yield_herd"), s.get("low_yield_herd")) if h]


def service_herds():
	"""The last rung of the ladder, plus cows already in milk.

	A heifer becomes servable at the top of the ladder; a cow becomes servable
	again once she is far enough past calving, which `service_wait_days` covers.
	"""
	herds = [r["herd"] for r in growth_ladder() if r["exits_on_service"]]
	return herds + milking_herds()


def service_wait_days():
	"""Days after calving before a cow is OFFERED for service again.

	The optimal window, not the minimum. Settings holds both: a hard floor
	(post_calving_min_service_days, 45 here) below which a service is refused,
	and the point the farm actually starts serving (60). Offering from the floor
	puts cows in front of the breeder three weeks before anybody would serve
	them; the floor stays where it is, guarding a deliberate override.
	"""
	s = settings()
	return int(s.get("post_calving_optimal_service_days")
	           or s.get("post_calving_min_service_days") or 0)


def is_milkable(animal):
	herd = frappe.db.get_value("Animal", animal, "current_herd")
	return bool(herd and herd in milking_herds())


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
	"""Animals with an open service, newest service first."""
	rows = frappe.db.sql(
		"""SELECT s.animal, MAX(s.service_date) AS served, MAX(s.name) AS service
		   FROM `tabLivestock Event` s
		   JOIN `tabAnimal` a ON a.name = s.animal
		   WHERE s.event_type = 'Service' AND s.docstatus = 1
		     AND s.pregnancy_confirmation_status = 'Pending'
		     AND IFNULL(a.status, '') NOT IN ('Dead','Deceased','Sold','Culled','Disposed')
		     AND IFNULL(a.disabled, 0) = 0
		   GROUP BY s.animal
		   ORDER BY served DESC
		   LIMIT 2000""",
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
	"""A cow that has not conceived within the farm's limit has expired from the
	high-yield herd on productivity grounds."""
	limit = int(settings().get("max_open_days") or 0)
	if not limit:
		return None
	days = open_days(animal)
	if days is None or days <= limit:
		return None
	return {"animal": animal, "open_days": days, "limit": limit, "days_over": days - limit}


# ---------------------------------------------------------------------------
# the dry herd, whose duration belongs to the route
# ---------------------------------------------------------------------------


def steamer_days_for(previous_herd):
	"""Dry days for an animal arriving in Steamers from `previous_herd`.

	Two streams meet here. A first-time heifer arrives with three months to
	calving; a cow from the low-yield herd arrives with two. Asking the herd
	would give one answer for both, which is why the journey is asked instead.
	"""
	s = settings()
	if previous_herd and previous_herd == s.get("incalf_heifer_herd"):
		return int(s.get("steamer_days_from_heifers") or 0)
	return int(s.get("steamer_days_from_lactation") or 0)


def expected_calving_date(conception_date):
	"""Conception plus gestation. Nine months, from settings."""
	days = int(settings().get("gestation_period_days") or 0) or 270
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

	Only the growth ladder — everything past it moves on breeding events, which
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


def bull_cull_warnings():
	"""Bull calves running out of selling window."""
	s = settings()
	herd = s.get("male_calf_herd")
	if not (s.get("cull_bulls_after_birth") and herd):
		return []
	out = []
	for a in _animals_in(herd):
		st = bull_cull_status(a["name"])
		if not st or not st["warn"]:
			continue
		out.append({
			"animal": a["name"],
			"label": _label(a),
			"herd": herd,
			"days_on_farm": st["days_on_farm"],
			"window_days": st["window_days"],
			"days_remaining": st["days_remaining"],
			"overdue": st["overdue"],
			"reason": "past the {}-day window by {} day(s)".format(
				st["window_days"], -st["days_remaining"])
			if st["overdue"] else "day {} of {}".format(st["days_on_farm"], st["window_days"]),
		})
	out.sort(key=lambda r: r["days_remaining"])
	return out


def open_cow_warnings():
	"""Cows that have gone too long without conceiving."""
	limit = int(settings().get("max_open_days") or 0)
	if not limit:
		return []
	out = []
	for herd in milking_herds():
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
	would keep her in the high-yield herd six weeks past the farm's own rule.
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


def lactation_move_due(animal):
	"""Is this cow due out of the herd she is milking in?

	THE LACTATING HERDS ARE NOT ON A CLOCK THE WAY THE CALF PENS ARE. A weaner
	leaves her pen because she has been in it long enough; a high yielder leaves
	because she is four months in calf and her yield is falling away, and those
	are not the same question. The farm's rule is written from CONCEPTION —
	`high_yield_days_from_conception` — so a cow served late stays where she is
	and a cow that caught early steps down early, which is the whole point.

	A cow who is not carrying is not due anywhere on this rule. She may be
	overdue on another (see `open_too_long`, which is about a cow who has failed
	to conceive at all) but she is not late for a move she has no reason to
	make.
	"""
	herd = frappe.db.get_value("Animal", animal, "current_herd")
	if not herd:
		return None
	s = settings()
	high, low = s.get("high_yield_herd"), s.get("low_yield_herd")
	steamers, incalf = s.get("steamer_herd"), s.get("incalf_heifer_herd")

	if herd not in (high, low, incalf) or not herd:
		return None

	conceived = conception_date(animal)
	if not conceived:
		return None
	days = date_diff(today(), conceived)
	calving = expected_calving_date(conceived)
	to_calving = date_diff(getdate(calving), today()) if calving else None

	if herd == high and low:
		limit = int(s.get("high_yield_days_from_conception") or 0)
		return _lactation_row(animal, herd, low, days, limit, to_calving,
		                      f"{days} days in calf") if limit else None

	if herd == low and steamers:
		# Two months in the low-yield herd, which the farm states as its own
		# number rather than as a second offset from conception — so it is read
		# as one, from the day she arrived.
		in_herd = days_in_current_herd(animal)
		limit = int(s.get("low_yield_days") or 0)
		if not limit or in_herd is None:
			return None
		return _lactation_row(animal, herd, steamers, in_herd, limit, to_calving,
		                      f"{in_herd} days in the low-yield herd")

	if herd == incalf and steamers:
		# A heifer is due out when calving is close, not when she has waited
		# long enough — she arrived already carrying.
		lead = int(s.get("steamer_days_from_heifers") or 0)
		if not lead or to_calving is None:
			return None
		return _lactation_row(
			animal, herd, steamers, lead - to_calving, 0, to_calving,
			f"{to_calving} days to calving", due=to_calving <= lead)
	return None


def _lactation_row(animal, herd, nxt, progress, limit, to_calving, reason, due=None):
	over = max(0, progress - limit) if limit else max(0, progress)
	return {
		"animal": animal,
		"herd": herd,
		"next_herd": nxt,
		"days_in_herd": progress,
		"days_expected": limit,
		"due": bool(due) if due is not None else bool(limit and progress >= limit),
		# A week past the farm's own number is late, not merely due. The calf
		# ladder has a `max_days_in_herd` for this; the lactation settings have
		# no second number, so the grace is stated here rather than invented per
		# call site.
		"overdue": (over > LACTATION_GRACE_DAYS) if (due is None or due) else False,
		"days_over": over,
		"days_to_calving": to_calving,
		"reason": reason,
	}


def lactation_suggestions():
	"""Every milking or in-calf animal whose move is due, soonest first."""
	s = settings()
	out = []
	for herd in [h for h in (s.get("high_yield_herd"), s.get("low_yield_herd"),
	                         s.get("incalf_heifer_herd")) if h]:
		for a in _animals_in(herd):
			row = lactation_move_due(a.name)
			if not row or not row["due"]:
				continue
			row["label"] = _label(a)
			row["from_herd"] = row.pop("herd")
			row["to_herd"] = row.pop("next_herd")
			out.append(row)
	out.sort(key=lambda r: (-r["days_over"], r["from_herd"]))
	return out


def suggestions():
	"""Everything the farm should look at, in one call."""
	growth = growth_suggestions()
	bulls = bull_cull_warnings()
	open_cows = open_cow_warnings()
	lactation = lactation_suggestions()
	return {
		# One list for the movement screen: a herdsman moving animals does not
		# care whether the rule behind a row counted days in a pen or days in
		# calf, only that she is due out.
		"growth": growth + lactation,
		"lactation": lactation,
		"bulls": bulls,
		"open_cows": open_cows,
		"counts": {
			"growth": len(growth) + len(lactation),
			"growth_overdue": sum(1 for r in growth + lactation if r["overdue"]),
			"lactation": len(lactation),
			"bulls": len(bulls),
			"bulls_overdue": sum(1 for r in bulls if r["overdue"]),
			"open_cows": len(open_cows),
		},
	}


# ---------------------------------------------------------------------------
# who each breeding screen may offer
#
# EVERY LIST HERE IS A NARROWING, and every threshold in it comes from Livestock
# Settings rather than from a number typed into this file. The farm moves its
# dry-off window or its gestation length on the Settings page and these lists
# move with it; a 60 written in here would be a second, disagreeing copy of the
# farm's own rule, which is exactly how api/reproduction.py came to answer 8
# animals ready where this package answered 2.
#
# The point of narrowing is not tidiness. An event recorded against an animal it
# cannot biologically have happened to does not stay a bad row: a drying-off
# moves her out of the milking herd and out of that herd's ration, a calving
# creates a calf, a confirmed pregnancy drives the feed forecast for months. The
# cheapest place to prevent all of that is the list the screen offers.
# ---------------------------------------------------------------------------


def dry_off_window_days(previous_herd=None):
	"""How long before calving a cow is taken out of milk.

	The same two streams `steamer_days_for` distinguishes: a first-time heifer
	dries off earlier than a cow coming off the low-yield herd. Asked by the
	herd she is standing in, because that is what the farm knows about her.
	"""
	s = settings()
	if previous_herd and previous_herd == s.get("incalf_heifer_herd"):
		return int(s.get("heifer_dry_off_before_calving_days")
		           or s.get("steamer_days_from_heifers") or 0)
	return int(s.get("steamer_days_from_lactation")
	           or s.get("heifer_dry_off_before_calving_days") or 0)


def _carrying_rows():
	"""Carrying cows with the date they conceived, keyed by animal."""
	return {r["animal"]: r for r in carrying_animals()}


def dried_off_on(animal, since=None):
	"""The day she was taken out of milk on this pregnancy, if she has been."""
	filters = {"animal": animal, "event_type": "Drying Off", "docstatus": 1}
	if since:
		filters["event_date"] = [">=", str(since)]
	row = frappe.get_all(
		"Livestock Event", filters=filters, fields=["event_date"],
		order_by="event_date desc", limit_page_length=1,
	)
	return str(row[0].event_date) if row and row[0].event_date else None


def dry_off_candidates():
	"""Cows to take out of milk: carrying, still milking, and near enough calving.

	THREE CONDITIONS AND ALL THREE MATTER. She has to be in calf, because drying
	off a cow who is not is throwing away a lactation for nothing. She has to be
	in milk, because there is nothing to dry off otherwise — and the screen
	offering a cow already standing in Steamers is what produced the duplicate
	drying-off events on this site. And she has to be close enough to calving,
	which is the farm's own window, not a judgement made here.
	"""
	milking = set(milking_herds())
	out = []
	for animal, row in _carrying_rows().items():
		herd = frappe.db.get_value("Animal", animal, "current_herd")
		if herd not in milking:
			continue
		if dried_off_on(animal, row.get("served")):
			continue
		due = expected_calving_date(conception_date(animal) or row.get("served"))
		if not due:
			continue
		window = dry_off_window_days(herd)
		days_to_calving = date_diff(getdate(due), getdate(today()))
		out.append({
			"animal": animal,
			"herd": herd,
			"due": str(due),
			"days_to_calving": days_to_calving,
			# She is ready when she is inside the farm's window. Cows outside it
			# still come back, marked, because a farm drying off early has a
			# reason and the screen should not pretend she does not exist.
			"ready": window and days_to_calving <= window,
			"window": window,
		})
	out.sort(key=lambda r: r["days_to_calving"])
	return out


def calving_candidates():
	"""Cows about to calve: carrying, dried off, and near their date.

	DRIED OFF IS PART OF IT, because that is the farm's sequence — a cow calves
	out of the dry herd, and one calving straight out of the milking herd is
	either a record entered in the wrong order or a cow nobody dried off, and
	both are worth seeing rather than silently accepting.

	The window is the gestation length plus the farm's calving alert lead, both
	from Settings. A cow past her date is still here, and first: overdue is the
	one state on this list that needs somebody to look at her today.
	"""
	lead = int(settings().get("calving_alert_lead_days") or 0)
	out = []
	for animal, row in _carrying_rows().items():
		conceived = conception_date(animal) or row.get("served")
		due = expected_calving_date(conceived)
		if not due:
			continue
		days_to_calving = date_diff(getdate(due), getdate(today()))
		dry_on = dried_off_on(animal, row.get("served"))
		out.append({
			"animal": animal,
			"herd": frappe.db.get_value("Animal", animal, "current_herd"),
			"due": str(due),
			"days_to_calving": days_to_calving,
			"dried_off_on": dry_on,
			"dried_off": bool(dry_on),
			# Ready to calve, by the farm's own lead time. Never a refusal —
			# calves arrive early, and a screen that refused to record one would
			# send the herdsman to the desk to do it anyway.
			"ready": bool(dry_on) and days_to_calving <= max(lead, 0),
		})
	out.sort(key=lambda r: r["days_to_calving"])
	return out


def service_age_months():
	"""How old a heifer must be before anybody serves her. From Settings."""
	return int(settings().get("min_service_age_months") or 0)


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
