# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One animal's family: her dam and sire, and every calf she or he left.

The phone keeps only the animals still on the farm, so a calf that was sold or
died is missing from its own table; this asks the record. Offspring are the
animals whose `dam` is her, or whose `sire` (the Animal link) is him, or —
for calves registered with only a sire's name written in — whose `sire_name`
is his id or burn name. Disposed calves come back too, with their status, so
the phone can grey them rather than lose them.

A male also gets his record as a sire, from the Service events that name him
(`sire_animal`): how many distinct females he has served, how many services,
the last one, and — where the pregnancy checks name him too — his conception
rate. What is not known is null, never zero.

Read-guarded on Animal.
"""

import frappe

from upande_livestock.serverscripts.common import animal_stage, thumbs
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run

FIELDS = ["name", "burn_name", "tag_number", "sex", "date_of_birth", "status", "disabled",
          "image", "current_herd"]


@frappe.whitelist()
def animal_family(payload=None):
	"""{parents: {dam, sire}, offspring: [...], sons, daughters, bred} for one animal."""

	def go():
		guard_read("Animal")
		d = as_dict(payload)
		name = (d.get("animal") or "").strip()
		if not name:
			frappe.throw(frappe._("Select an animal."))
		a = frappe.db.get_value(
			"Animal", name, ["name", "burn_name", "sex", "dam", "sire", "sire_name", "stream", "current_herd"],
			as_dict=True)
		if not a:
			frappe.throw(frappe._("{0} is not an animal on this farm.").format(name))
		return {"ok": True, "id": a.name, **family(a)}

	return run(go, "livestock animal_family failed")


def family(a):
	offspring = [_card(r) for r in _offspring(a)]
	bred = sire_record(a.name) if a.sex == "Male" else None
	return {
		"parents": {"dam": _parent(a.dam), "sire": _parent(a.sire) or _named_sire(a.sire_name)},
		"offspring": offspring,
		"sons": sum(1 for o in offspring if o["sex"] == "Male"),
		"daughters": sum(1 for o in offspring if o["sex"] == "Female"),
		"bred": bred,
		"breedingBull": is_breeding_male(a, bred, offspring),
	}


def is_breeding_male(a, bred, offspring):
	"""A male kept for breeding: the Breeding stream, a Breeding-class herd, or a
	sire on record (a service names him, or a calf does)."""
	if a.sex != "Male":
		return False
	if animal_stage.is_breeding_bull(a) or (bred and bred["services"]) or offspring:
		return True
	return bool(a.current_herd) and frappe.db.get_value("Herds", a.current_herd, "herd_class") == "Breeding"


def sire_record(name):
	"""His services as a sire: distinct females, services, last service, conception rate."""
	row = frappe.db.sql(
		"""select count(*) as services, count(distinct animal) as cows, max(event_date) as last
		from `tabLivestock Event`
		where docstatus = 1 and event_type = 'Service' and sire_animal = %s""", (name,), as_dict=True)[0]
	services = row.services or 0
	conceptions = frappe.db.sql(
		"""select count(*) from `tabLivestock Event`
		where docstatus = 1 and event_type = 'Pregnancy Diagnosis'
		  and diagnosis_result = 'Confirmed' and sire_animal = %s""", (name,))[0][0] or 0
	return {
		"cows": row.cows or 0,
		"services": services,
		"lastService": str(row.last) if row.last else None,
		"conceptions": conceptions,
		# Null, not zero: a bull with no service on record has no rate.
		"conceptionRate": min(100, round(conceptions * 100.0 / services)) if services else None,
	}


def _offspring(a):
	names = [x for x in {a.name, a.burn_name} if x]
	if a.sex == "Female":
		filters = {"dam": a.name}
		or_filters = None
	elif a.sex == "Male":
		filters = None
		or_filters = {"sire": a.name, "sire_name": ["in", names]}
	else:
		filters = None
		or_filters = {"dam": a.name, "sire": a.name}
	rows = frappe.get_all("Animal", filters=filters, or_filters=or_filters, fields=FIELDS,
	                      order_by="date_of_birth desc, name asc", limit_page_length=0)
	return [r for r in rows if r.name != a.name]


def _parent(name):
	if not name:
		return None
	r = frappe.db.get_value("Animal", name, FIELDS, as_dict=True)
	return _card(r) if r else {"id": name, "name": name, "tag": None, "sex": None, "dob": None,
	                            "status": None, "active": False, "photo": None, "thumb": None,
	                            "onRecord": False}


def _named_sire(text):
	"""A sire written in by name only (A.I. bull, or a bull not on the farm)."""
	if not text:
		return None
	match = frappe.db.get_value("Animal", {"burn_name": text}, "name") or (
		text if frappe.db.exists("Animal", text) else None)
	if match:
		return _parent(match)
	return {"id": None, "name": text, "tag": None, "sex": "Male", "dob": None, "status": None,
	        "active": False, "photo": None, "thumb": None, "onRecord": False}


def _card(r):
	active = not r.disabled and r.status not in animal_stage.RETIRED
	return {
		"id": r.name,
		"name": r.burn_name or r.name,
		"tag": r.tag_number,
		"sex": r.sex,
		"dob": str(r.date_of_birth) if r.date_of_birth else None,
		"status": r.status or ("Disabled" if r.disabled else None),
		"active": bool(active),
		"herd": r.current_herd,
		"photo": r.image,
		"thumb": thumbs.existing_thumb(r.image) if r.image else None,
		"onRecord": True,
	}
