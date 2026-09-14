# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One animal's whole life, as the Animals page draws it.

The page was built against a sample: real Kaitet register numbers and real herd
names, so the layout met "12 MONTHS-SERVICE (BULLYING HEIFERS)" before a farm
did, but invented figures. This is the same shapes, filled from the record.

HER TIMELINE IS HER EVENTS, not a summary of them. Every milestone here is one
Livestock Event that somebody submitted, on the date they submitted it for —
which is why a backdated calving appears where it happened rather than where it
was typed. The herd bands underneath come from the Movement events, so a gap in
them is a gap in what the farm recorded, not something smoothed over.

WHAT IS NOT KNOWN IS NULL, NEVER ZERO. A heifer who has never been served has
no conception rate; reporting 0% would read as a cow who has failed every
service, which is the opposite of the truth and exactly the figure somebody
culls on.

Read-guarded on Animal.
"""

from itertools import pairwise

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run

RETIRED = ("Dead", "Deceased", "Sold", "Culled", "Disposed", "Transferred Out")

#: Which event types earn a mark on the timeline, and what to call them.
MILESTONES = {
	"Birth": ("birth", "Born"),
	"Movement": ("movement", "Moved"),
	"Service": ("service", "Served"),
	"Pregnancy Diagnosis": ("confirmed", "Checked"),
	"Calving": ("calving", "Calved"),
	"Abortion": ("abortion", "Lost the pregnancy"),
	"Drying Off": ("drying", "Dried off"),
	"Check Up": ("health", "Seen"),
	"Health Case": ("health", "Case opened"),
	"Weight Recording": ("weight", "Weighed"),
	"Vaccination": ("health", "Vaccinated"),
	"Deworming": ("health", "Dewormed"),
	"Cull Review": ("health", "Marked for review"),
}


@frappe.whitelist()
def animal_profile(payload=None):
	"""Everything the Animals page shows about one animal."""

	def go():
		guard_read("Animal")
		d = as_dict(payload)
		name = (d.get("animal") or "").strip()
		if not name:
			frappe.throw(frappe._("Select an animal."))
		a = frappe.db.get_value(
			"Animal", name,
			["name", "burn_name", "sex", "current_herd", "breed", "date_of_birth",
			 "status", "disabled", "image", "dam", "sire_name", "repro_status"],
			as_dict=True)
		if not a:
			frappe.throw(frappe._("{0} is not an animal on this farm.").format(name))

		events = frappe.get_all(
			"Livestock Event",
			filters={"animal": name, "docstatus": 1},
			fields=["name", "event_type", "event_date", "current_herd", "new_herd",
			        "service_type", "diagnosis_result", "expected_calving_date",
			        "custom_calving_outcome", "abortion_cause", "remarks"],
			order_by="event_date asc, creation asc",
		)

		last_calving = _last(events, "Calving")
		expected = _expected_calving(events)
		cycle = _cycle(a, events, last_calving, expected)

		return {
			"ok": True,
			"id": a.name,
			"name": a.burn_name or a.name,
			"sex": a.sex,
			"herd": a.current_herd or "no herd",
			"breed": a.breed,
			"bornOn": str(a.date_of_birth) if a.date_of_birth else None,
			"status": a.status,
			"stage": cycle["stage"],
			"photo": a.image,
			"dam": a.dam,
			"sire": a.sire_name,
			"lastCalving": last_calving,
			"expectedCalving": expected,
			"cycle": cycle,
			"kpis": _kpis(name, events, a),
			"milestones": _milestones(events),
			"spells": _spells(a, events),
		}

	return run(go, "livestock animal_profile failed")


def _last(events, event_type):
	dates = [str(e.event_date) for e in events if e.event_type == event_type and e.event_date]
	return dates[-1] if dates else None


def _expected_calving(events):
	"""The date the farm is actually watching for, if she is carrying.

	Read off the pregnancy rather than re-derived from the service date plus a
	gestation constant: a vet may have corrected it by hand, and re-deriving
	would quietly overrule the correction.
	"""
	for e in reversed(events):
		if e.event_type == "Calving":
			return None          # the pregnancy that expected one is over
		if e.expected_calving_date:
			return str(e.expected_calving_date)
	return None


def _cycle(a, events, last_calving, expected):
	"""Where she stands in the loop between one calving and the next."""
	if a.disabled or a.status in RETIRED:
		return {"stage": "retired", "dayInStage": 0, "daysInMilk": None,
		        "nextUp": "She has left the farm", "nextOn": None}

	dim = date_diff(today(), getdate(last_calving)) if last_calving else None
	served = _last(events, "Service")
	dried = _last(events, "Drying Off")
	confirmed = None
	for e in reversed(events):
		if e.event_type == "Calving":
			break
		if e.event_type == "Pregnancy Diagnosis" and e.diagnosis_result == "Confirmed":
			confirmed = str(e.event_date)
			break

	def since(d):
		return date_diff(today(), getdate(d)) if d else 0

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
		return {"stage": "heifer", "dayInStage": since(a.date_of_birth), "daysInMilk": None,
		        "nextUp": "First service", "nextOn": None}
	if dim is not None and dim <= 60:
		return {"stage": "fresh", "dayInStage": dim, "daysInMilk": dim,
		        "nextUp": "Ready to serve", "nextOn": add_days(last_calving, 60)}
	return {"stage": "open", "dayInStage": dim or 0, "daysInMilk": dim,
	        "nextUp": "Service", "nextOn": None}


def _kpis(name, events, a):
	"""Her figures. Null where the farm has not recorded enough to say."""
	calvings = [str(e.event_date) for e in events if e.event_type == "Calving" and e.event_date]
	services = sum(1 for e in events if e.event_type == "Service")
	abortions = sum(1 for e in events if e.event_type == "Abortion")
	conceptions = sum(
		1 for e in events
		if e.event_type == "Pregnancy Diagnosis" and e.diagnosis_result == "Confirmed")

	interval = None
	if len(calvings) >= 2:
		gaps = [date_diff(getdate(b), getdate(x)) for x, b in pairwise(calvings)]
		interval = round(sum(gaps) / len(gaps))

	year_ago = add_days(today(), -365)
	treatments = frappe.db.count("Livestock Event", {
		"animal": name, "docstatus": 1, "event_date": [">=", year_ago],
		"event_type": ["in", ("Check Up", "Health Case", "Vaccination", "Deworming")],
	})

	return {
		"parity": len(calvings),
		"services": services,
		"conceptions": conceptions,
		"abortions": abortions,
		# Null, not zero: a heifer who has never been served has no rate, and
		# 0% reads as a cow who has failed every service.
		"conceptionRate": round(conceptions * 100.0 / services) if services else None,
		"calvingInterval": interval,
		# Per-animal milk is not recorded on this farm — Milk Recording is per
		# herd per session — so these stay null rather than inventing a share.
		"lactationYield": None,
		"yieldIndex": None,
		"treatments": treatments,
	}


def _milestones(events):
	out = []
	for e in events:
		if not e.event_date:
			continue
		spec = MILESTONES.get(e.event_type)
		if not spec:
			continue
		kind, label = spec
		detail = None
		if e.event_type == "Movement" and e.new_herd:
			detail = f"{e.current_herd or 'nowhere'} → {e.new_herd}"
		elif e.event_type == "Service" and e.service_type:
			detail = e.service_type
		elif e.event_type == "Pregnancy Diagnosis" and e.diagnosis_result:
			detail = e.diagnosis_result
		elif e.event_type == "Calving" and e.custom_calving_outcome:
			detail = e.custom_calving_outcome
		elif e.event_type == "Abortion" and e.abortion_cause:
			detail = e.abortion_cause
		elif e.remarks:
			detail = e.remarks[:120]
		out.append({"kind": kind, "on": str(e.event_date), "label": label, "detail": detail})
	return out


def _spells(a, events):
	"""The stretches of her life spent in one herd, from the moves themselves.

	A gap is a gap in what the farm recorded, not something smoothed over: if
	her first Movement is dated after her birth, the band starts at the move.

	THE LAST BAND IS WHERE SHE ACTUALLY IS, which is not always where her last
	Movement put her. 64 animals on this site stand in a herd their movement
	history does not account for — the register load and the holding-herd sweep
	wrote `current_herd` directly, so the moves were never recorded. Drawing the
	band from the last move would show a cow in Lactating group 1 while she is
	standing in STEAMERS. The band says where she is and `unrecorded` says the
	move behind it was never written down, so the gap is visible rather than
	papered over.
	"""
	moves = [e for e in events if e.event_type == "Movement" and e.new_herd and e.event_date]
	spells = []
	if moves:
		first = moves[0]
		if first.current_herd and a.date_of_birth:
			spells.append({"herd": first.current_herd, "from": str(a.date_of_birth),
			               "to": str(first.event_date), "unrecorded": False})
		for i, m in enumerate(moves):
			nxt = moves[i + 1] if i + 1 < len(moves) else None
			spells.append({"herd": m.new_herd, "from": str(m.event_date),
			               "to": str(nxt.event_date) if nxt else None, "unrecorded": False})
	elif a.current_herd:
		spells.append({"herd": a.current_herd,
		               "from": str(a.date_of_birth) if a.date_of_birth else None,
		               "to": None, "unrecorded": False})

	spells = [s for s in spells if s["from"]]

	if a.current_herd and spells and spells[-1]["herd"] != a.current_herd:
		spells[-1]["to"] = spells[-1]["to"] or str(getdate(today()))
		spells.append({"herd": a.current_herd, "from": spells[-1]["to"],
		               "to": None, "unrecorded": True})
	return spells
