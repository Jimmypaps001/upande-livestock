# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where an animal stands in its life cycle — one rule, two callers.

THE CYCLE FOLLOWS THE ANIMAL'S SEX. A female runs the reproductive loop (heifer,
served, in calf, fresh, open). A male that is not a breeding bull runs a
liveweight growth ladder (calf, weaner, grower, finisher, market). A male in the
breeding stream is a "bull", whose rest/breeding status is `bull_status`. A
missing or unknown sex gets no cycle at all ("unknown"), never a wrong one.

`animals/animal_profile` draws it for one animal on the Animals page;
`mobile/animals_since` hands it to the phone for every animal at once so the
badge works offline. Both ask here, so the stage a farmer sees on the phone is
the stage the desk shows.

The stage is a function of four facts, all from submitted events (plus the
animal's own row): the last calving, last service, the
latest CONFIRMED pregnancy diagnosis after that calving, and today. `facts_for`
reads them for many animals in a few grouped queries; `facts_from_events` reads
them from an event list already in hand.

The stage moves with TIME as well as with events — "fresh" turns to "open" on
day 61 with nobody recording anything. `moved_since` says which animals a delta
sync must resend for either reason.
"""

import frappe
from frappe.utils import add_days, add_months, date_diff, flt, getdate, today

RETIRED = ("Dead", "Deceased", "Sold", "Culled", "Disposed", "Transferred Out")

#: Livestock Event types the stage is read from.
STAGE_EVENT_TYPES = ("Calving", "Service", "Pregnancy Diagnosis")

FRESH_DAYS = 60

#: The growth ladder a male on feed climbs, lowest first.
GROWTH_STAGES = ("calf", "weaner", "grower", "finisher", "market")

#: Stage of an unweighed male once he is past weaning age.
UNWEIGHED_MALE = "steer"


def growth_thresholds():
	"""[(stage, from_kg)] for the growth ladder, lowest first.

	From the farm's Fattening herd bands when it has three or more (the second
	band's minimum starts "grower", the third's starts "finisher": Starters /
	Growers / Finishers), else from the Livestock Settings fields `stage_*_kg`.
	"market" starts at Target Exit Weight.
	"""
	from upande_livestock.serverscripts.common.timings import get_timing

	bands = sorted(
		flt(m) for m in frappe.get_all(
			"Herds", filters={"herd_class": "Fattening", "min_weight_kg": [">", 0]},
			pluck="min_weight_kg"))
	grower = bands[0] if len(bands) >= 2 else get_timing("stage_grower_kg")
	finisher = bands[1] if len(bands) >= 2 else get_timing("stage_finisher_kg")
	market = flt(frappe.db.get_single_value("Livestock Settings", "target_exit_weight_kg")) or 450.0
	out = [("calf", 0.0), ("weaner", float(get_timing("stage_weaner_kg"))),
	       ("grower", float(grower)), ("finisher", float(finisher)), ("market", market)]
	# a misconfigured ladder must still climb
	for i in range(1, len(out)):
		if out[i][1] <= out[i - 1][1]:
			out[i] = (out[i][0], out[i - 1][1] + 1)
	return out


def growth_position(kg):
	"""{stage, fromKg, nextStage, nextKg, pct} for a liveweight, or None without one.

	`pct` is how far through the current band he is; the top stage has no next.
	"""
	if not kg or kg <= 0:
		return None
	ladder = growth_thresholds()
	i = max(j for j, (_, lo) in enumerate(ladder) if kg >= lo)
	stage, lo = ladder[i]
	if i + 1 >= len(ladder):
		return {"stage": stage, "fromKg": lo, "nextStage": None, "nextKg": None, "pct": 100}
	nxt, hi = ladder[i + 1]
	return {"stage": stage, "fromKg": lo, "nextStage": nxt, "nextKg": hi,
	        "pct": max(0, min(99, round((kg - lo) * 100.0 / (hi - lo))))}


def is_breeding_bull(a):
	return a.get("sex") == "Male" and a.get("stream") == "Breeding"


def bull_class(a, on=None):
	""""Breeding bull", or "Young bull" before the farm's minimum breeding age."""
	from upande_livestock.serverscripts.common.timings import get_timing

	if not a.get("date_of_birth"):
		return "Breeding bull"
	ripe = add_months(getdate(a["date_of_birth"]), get_timing("breeding_bull_min_age_months"))
	return "Breeding bull" if ripe <= getdate(on or today()) else "Young bull"


def bull_status(name, herd, on=None):
	"""{state, since, reason} - "In breeding cycle" or "At rest", from the data.

	IN THE BREEDING CYCLE when either holds:
	  1. he stands in a Breeding-class herd that also holds at least one live
	     female (a mating group; the Bull Reserve holds only bulls), or
	  2. a submitted Service names him (`sire_animal`) within the last
	     `bull_service_window_days` (Livestock Settings, default 60).
	Otherwise AT REST.
	"""
	from upande_livestock.serverscripts.common.timings import get_timing

	on = getdate(on or today())
	window = get_timing("bull_service_window_days")
	last = frappe.db.sql(
		"""select max(event_date) from `tabLivestock Event`
		where docstatus = 1 and event_type = 'Service' and sire_animal = %s""", (name,))[0][0]
	if last and date_diff(on, getdate(last)) <= window:
		return {"state": "In breeding cycle", "lastService": _d(last),
		        "reason": f"served a female {date_diff(on, getdate(last))} days ago"}
	with_females = 0
	if herd and frappe.db.get_value("Herds", herd, "herd_class") == "Breeding":
		with_females = frappe.db.count("Animal", {
			"current_herd": herd, "sex": "Female", "disabled": 0, "status": "Active"})
	if with_females:
		return {"state": "In breeding cycle", "lastService": _d(last),
		        "reason": f"running with {with_females} females in {herd}"}
	return {"state": "At rest", "lastService": _d(last),
	        "reason": "not with a mating group and no service in the last %s days" % window}


def _d(value):
	return str(value) if value else None


def facts_from_events(events):
	"""The stage facts from one animal's submitted events (any order)."""
	facts = {"calving": None, "service": None, "confirmed": None}
	confirmed_dates = []
	for e in events:
		if not e.event_date:
			continue
		date = str(e.event_date)
		key = {"Calving": "calving", "Service": "service"}.get(e.event_type)
		if key:
			facts[key] = max(facts[key] or date, date)
		elif e.event_type == "Pregnancy Diagnosis" and e.diagnosis_result == "Confirmed":
			confirmed_dates.append(date)
	if confirmed_dates:
		facts["confirmed"] = max(confirmed_dates)
	return facts


def facts_for(names):
	"""{animal: facts} for many animals, in two queries however many there are."""
	out = {n: {"calving": None, "service": None, "confirmed": None} for n in names}
	if not names:
		return out
	rows = frappe.db.sql(
		"""select animal, event_type, diagnosis_result = 'Confirmed' as confirmed, max(event_date) as last
		from `tabLivestock Event`
		where docstatus = 1 and animal in %(names)s and event_type in %(types)s
		group by animal, event_type, confirmed""",
		{"names": tuple(names), "types": STAGE_EVENT_TYPES},
		as_dict=True,
	)
	key = {"Calving": "calving", "Service": "service"}
	for r in rows:
		if not r.last:
			continue
		f = out[r.animal]
		if r.event_type in key:
			f[key[r.event_type]] = max(f[key[r.event_type]] or _d(r.last), _d(r.last))
		elif r.event_type == "Pregnancy Diagnosis" and r.confirmed:
			f["confirmed"] = max(f["confirmed"] or _d(r.last), _d(r.last))
	return out


def cycle(a, facts, expected=None, on=None):
	"""The cycle dict for animal row `a` (disabled, status, date_of_birth) and `facts`."""
	on = on or today()
	if a.get("disabled") or a.get("status") in RETIRED:
		return {"kind": "retired", "stage": "retired", "dayInStage": 0,
		        "nextUp": "She has left the farm", "nextOn": None}

	sex = a.get("sex")
	if sex == "Male":
		return _male_cycle(a, on)
	if sex != "Female":
		return {"kind": "unknown", "stage": "unknown", "dayInStage": 0,
		        "nextUp": "Record the animal's sex", "nextOn": None}

	last_calving = facts.get("calving")
	served = facts.get("service")
	since_calving = date_diff(on, getdate(last_calving)) if last_calving else None
	confirmed = facts.get("confirmed")
	if confirmed and last_calving and getdate(confirmed) <= getdate(last_calving):
		confirmed = None  # that pregnancy ended in the calving

	def since(d):
		return date_diff(on, getdate(d)) if d else 0

	def out(d):
		return {"kind": "repro", **d}

	if confirmed:
		return out({"stage": "confirmed", "dayInStage": since(confirmed),
		            "nextUp": "Calving", "nextOn": expected})
	if served and (not last_calving or getdate(served) > getdate(last_calving)):
		return out({"stage": "served", "dayInStage": since(served),
		            "nextUp": "Pregnancy check", "nextOn": add_days(served, 35)})
	if not last_calving:
		from upande_livestock.serverscripts.common.timings import get_timing

		age = since(a.get("date_of_birth")) if a.get("date_of_birth") else None
		if age is not None and age < get_timing("calf_separation_age_days"):
			return out({"stage": "calf", "dayInStage": age, "nextUp": "Weaning", "nextOn": None})
		return out({"stage": "heifer", "dayInStage": since(a.get("date_of_birth")),
		            "nextUp": "First service", "nextOn": None})
	if since_calving is not None and since_calving <= FRESH_DAYS:
		return out({"stage": "fresh", "dayInStage": since_calving,
		            "nextUp": "Ready to serve", "nextOn": add_days(last_calving, FRESH_DAYS)})
	return out({"stage": "open", "dayInStage": since_calving or 0,
	            "nextUp": "Service", "nextOn": None})


def _male_cycle(a, on):
	from upande_livestock.serverscripts.common.timings import get_timing

	if is_breeding_bull(a):
		return {"kind": "bull", "stage": "bull", "dayInStage": 0,
		        "nextUp": "", "nextOn": None, "class": bull_class(a, on)}
	pos = growth_position(flt(a.get("last_weight_kg")))
	if pos:
		return {"kind": "growth", "stage": pos["stage"], "dayInStage": 0,
		        "nextUp": ("Reaches %s at %s kg" % (pos["nextStage"], round(pos["nextKg"]))
		                   if pos["nextStage"] else "Ready for sale"),
		        "nextOn": None}
	# no weighing: age alone can say "calf", and nothing more
	age = date_diff(on, getdate(a["date_of_birth"])) if a.get("date_of_birth") else None
	if age is not None and age < get_timing("calf_separation_age_days"):
		return {"kind": "growth", "stage": "calf", "dayInStage": age,
		        "nextUp": "Weigh him to place him on the growth ladder", "nextOn": None}
	return {"kind": "growth", "stage": UNWEIGHED_MALE, "dayInStage": 0,
	        "nextUp": "Weigh him to place him on the growth ladder", "nextOn": None}


def _with_male_facts(rows):
	"""Rows with `stream` and `last_weight_kg` filled in when the caller's query left them out."""
	need = [r["name"] for r in rows if "stream" not in r or "last_weight_kg" not in r]
	if not need:
		return rows
	extra = {x.name: x for x in frappe.get_all(
		"Animal", filters={"name": ["in", need]}, fields=["name", "stream", "last_weight_kg", "sex"],
		limit_page_length=0)}
	return [{**{"stream": None, "last_weight_kg": None}, **dict(r), **{
		k: v for k, v in (extra.get(r["name"]) or {}).items() if k not in r}} for r in rows]


def stages_for(rows):
	"""{animal name: stage} for animal rows (name, disabled, status, date_of_birth)."""
	rows = _with_male_facts(rows)
	facts = facts_for([r["name"] for r in rows])
	return {r["name"]: cycle(r, facts[r["name"]])["stage"] for r in rows}


def moved_since(since_ts):
	"""Names of animals whose stage may have changed after `since_ts`.

	By EVENT: a stage-bearing Livestock Event created, submitted, cancelled or
	amended since (they all move the event's `modified`) — this reads the events,
	which is where a stage comes from, rather than relying on every write path
	remembering to touch the Animal. By TIME: an animal calved in the window
	that turned fresh -> open since then.
	"""
	names = set(frappe.db.sql_list(
		"""select distinct animal from `tabLivestock Event`
		where modified > %s and event_type in %s and animal is not null""",
		(since_ts, STAGE_EVENT_TYPES),
	))
	lo = add_days(getdate(since_ts), -FRESH_DAYS - 1)
	hi = add_days(getdate(today()), -FRESH_DAYS)
	names |= set(frappe.db.sql_list(
		"""select distinct animal from `tabLivestock Event`
		where docstatus = 1 and event_type = 'Calving' and event_date between %s and %s
		and animal is not null""",
		(lo, hi),
	))
	return names
