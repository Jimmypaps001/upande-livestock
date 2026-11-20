# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One animal's family: her dam and sire, and every calf she or he left.

The phone keeps only the animals still on the farm, so a calf that was sold or
died is missing from its own table; this asks the record. Offspring are the
animals whose `dam` is her, or whose `sire_name` (free text) is his id or
burn name. Kaitet's Animal has no `sire` link; a site that does have one
(Mutara) is honoured too, and any parent field a site lacks is simply skipped. Disposed calves come back too, with their status, so
the phone can grey them rather than lose them.

A male also gets his record as a sire, from the Service events that name him
(`sire`, or `sire_animal` where a site has it): how many distinct females he has served, how many services,
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
		cols = [c for c in ("name", "burn_name", "sex", "dam", "sire", "sire_name", "current_herd")
		        if c == "name" or _has("Animal", c)]
		a = frappe.db.get_value("Animal", name, cols, as_dict=True)
		if not a:
			frappe.throw(frappe._("{0} is not an animal on this farm.").format(name))
		return {"ok": True, "id": a.name, **family(a)}

	return run(go, "livestock animal_family failed")


def _has(doctype, fieldname):
	return bool(frappe.get_meta(doctype).has_field(fieldname))


def family(a):
	a = frappe._dict(a)
	offspring = [_card(r) for r in _offspring(a)]
	bred = sire_record(a) if a.get("sex") == "Male" else None
	return {
		"parents": {"dam": _parent(a.get("dam")),
		            "sire": _parent(a.get("sire")) or _named_sire(a.get("sire_name"))},
		"offspring": offspring,
		"sons": sum(1 for o in offspring if o["sex"] == "Male"),
		"daughters": sum(1 for o in offspring if o["sex"] == "Female"),
		"bred": bred,
	}


def sire_record(a):
	"""His services as a sire: distinct females, services, last service, conception rate.

	Kaitet's Livestock Event names the sire as text in `sire` (his id or burn name);
	a site with a `sire_animal` link uses that. Neither column present: no record."""
	a = frappe._dict(a) if not isinstance(a, str) else frappe._dict(name=a)
	col = next((c for c in ("sire_animal", "sire") if _has("Livestock Event", c)), None)
	if not col:
		return None
	names = tuple({x for x in (a.name, a.get("burn_name")) if x})
	row = frappe.db.sql(
		f"""select count(*) as services, count(distinct animal) as cows, max(event_date) as last
		from `tabLivestock Event`
		where docstatus = 1 and event_type = 'Service' and `{col}` in %s""", (names,), as_dict=True)[0]
	services = row.services or 0
	conceptions = frappe.db.sql(
		f"""select count(*) from `tabLivestock Event`
		where docstatus = 1 and event_type = 'Pregnancy Diagnosis'
		  and diagnosis_result = 'Confirmed' and `{col}` in %s""", (names,))[0][0] or 0
	return {
		"cows": row.cows or 0,
		"services": services,
		"lastService": str(row.last) if row.last else None,
		"conceptions": conceptions,
		# Null, not zero: a bull with no service on record has no rate.
		"conceptionRate": min(100, round(conceptions * 100.0 / services)) if services else None,
	}


def _offspring(a):
	names = [x for x in {a.name, a.get("burn_name")} if x]
	sex = a.get("sex")
	by_dam = {"dam": a.name} if _has("Animal", "dam") else None
	by_sire = {}
	if _has("Animal", "sire"):
		by_sire["sire"] = a.name
	if _has("Animal", "sire_name"):
		by_sire["sire_name"] = ["in", names]
	or_filters = {}
	if sex == "Female":
		or_filters = by_dam or {}
	elif sex == "Male":
		or_filters = by_sire
	else:
		or_filters = {**(by_dam or {}), **by_sire}
	if not or_filters:
		return []
	rows = frappe.get_all("Animal", or_filters=or_filters, fields=FIELDS,
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
