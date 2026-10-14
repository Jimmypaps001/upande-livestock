# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where an animal stands in her calving cycle — one rule, two callers.

`animals/animal_profile` draws it for one animal on the Animals page;
`mobile/animals_since` hands it to the phone for every animal at once so the
badge works offline. Both ask here, so the stage a farmer sees on the phone is
the stage the desk shows.

The stage is a function of five facts, all from submitted events (plus the
animal's own row): the last calving, last service and last drying off, the
latest CONFIRMED pregnancy diagnosis after that calving, and today. `facts_for`
reads them for many animals in a few grouped queries; `facts_from_events` reads
them from an event list already in hand.

The stage moves with TIME as well as with events — "fresh" turns to "open" on
day 61 with nobody recording anything. `moved_since` says which animals a delta
sync must resend for either reason.
"""

import frappe
from frappe.utils import add_days, date_diff, getdate, today

RETIRED = ("Dead", "Deceased", "Sold", "Culled", "Disposed", "Transferred Out")

#: Livestock Event types the stage is read from.
STAGE_EVENT_TYPES = ("Calving", "Service", "Drying Off", "Pregnancy Diagnosis")

FRESH_DAYS = 60


def _d(value):
	return str(value) if value else None


def facts_from_events(events):
	"""The stage facts from one animal's submitted events (any order)."""
	facts = {"calving": None, "service": None, "drying": None, "confirmed": None}
	confirmed_dates = []
	for e in events:
		if not e.event_date:
			continue
		date = str(e.event_date)
		key = {"Calving": "calving", "Service": "service", "Drying Off": "drying"}.get(e.event_type)
		if key:
			facts[key] = max(facts[key] or date, date)
		elif e.event_type == "Pregnancy Diagnosis" and e.diagnosis_result == "Confirmed":
			confirmed_dates.append(date)
	if confirmed_dates:
		facts["confirmed"] = max(confirmed_dates)
	return facts


def facts_for(names):
	"""{animal: facts} for many animals, in two queries however many there are."""
	out = {n: {"calving": None, "service": None, "drying": None, "confirmed": None} for n in names}
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
	key = {"Calving": "calving", "Service": "service", "Drying Off": "drying"}
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
		return {"stage": "retired", "dayInStage": 0, "daysInMilk": None,
		        "nextUp": "She has left the farm", "nextOn": None}

	last_calving = facts.get("calving")
	served, dried = facts.get("service"), facts.get("drying")
	dim = date_diff(on, getdate(last_calving)) if last_calving else None
	confirmed = facts.get("confirmed")
	if confirmed and last_calving and getdate(confirmed) <= getdate(last_calving):
		confirmed = None  # that pregnancy ended in the calving

	def since(d):
		return date_diff(on, getdate(d)) if d else 0

	if dried and (not last_calving or getdate(dried) > getdate(last_calving)):
		return {"stage": "dry", "dayInStage": since(dried), "daysInMilk": dim,
		        "nextUp": "Calving", "nextOn": expected}
	if confirmed:
		return {"stage": "confirmed", "dayInStage": since(confirmed), "daysInMilk": dim,
		        "nextUp": "Drying off, then calving", "nextOn": expected}
	if served and (not last_calving or getdate(served) > getdate(last_calving)):
		return {"stage": "served", "dayInStage": since(served), "daysInMilk": dim,
		        "nextUp": "Pregnancy check", "nextOn": add_days(served, 35)}
	if not last_calving:
		return {"stage": "heifer", "dayInStage": since(a.get("date_of_birth")), "daysInMilk": None,
		        "nextUp": "First service", "nextOn": None}
	if dim is not None and dim <= FRESH_DAYS:
		return {"stage": "fresh", "dayInStage": dim, "daysInMilk": dim,
		        "nextUp": "Ready to serve", "nextOn": add_days(last_calving, FRESH_DAYS)}
	return {"stage": "open", "dayInStage": dim or 0, "daysInMilk": dim,
	        "nextUp": "Service", "nextOn": None}


def stages_for(rows):
	"""{animal name: stage} for animal rows (name, disabled, status, date_of_birth)."""
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
