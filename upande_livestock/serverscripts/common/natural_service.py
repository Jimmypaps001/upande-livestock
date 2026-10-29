# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Natural service is recorded when it is perceived, from any of three places.

1. the Service entry, type Natural, with the date the mating was seen;
2. a Pregnancy Diagnosis with no open service: the vet's perceived conception
   date (or the foetal age in weeks), from which the service is derived;
3. a Calving with no confirmed pregnancy: conception is the calving date minus
   the gestation period.

All three resolve to one Natural Service event carrying `conception_date`, so
what follows (the diagnosis, the calving, the calf's sire) is the chain the
Kaitet dairy flow already runs. A service made here is SYSTEM-DERIVED: it is
dated in the past and flagged backdated even while the farm's backdating window
is closed, because the system worked the date out, not the user.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate

from upande_livestock.serverscripts.common.timings import get_timing


def conception_from(d, diagnosis_date):
	"""The perceived conception date a diagnosis payload carries, or None."""
	if d.get("conception_date"):
		return str(getdate(d["conception_date"]))
	weeks = d.get("foetal_age_weeks")
	if weeks not in (None, ""):
		return str(add_days(getdate(diagnosis_date), -int(float(weeks) * 7)))
	return None


def create_natural_service(animal, conception_date, operator=None, sire_animal=None,
                           sire_unknown=False, remarks=None):
	"""Insert and submit a Natural Service at `conception_date`; returns the event."""
	from upande_livestock.serverscripts.common.events import new_livestock_event

	doc = new_livestock_event(
		{"animal": animal, "operator": operator, "event_date": str(getdate(conception_date)),
		 "remarks": remarks},
		"Service", date_key="service_date", derived=True)
	doc.service_type = "Natural"
	doc.service_date = doc.event_date
	doc.conception_date = doc.event_date
	if sire_animal:
		doc.sire_animal = sire_animal
	doc.flags.sire_unknown = bool(sire_unknown)
	doc.insert()
	doc.submit()
	return doc


def sire_report(service):
	"""The sire facts an endpoint returns for a saved Service document or name."""
	doc = frappe.get_doc("Livestock Event", service) if isinstance(service, str) else service
	inferred = doc.flags.get("sire_inference") or {}
	label = ""
	if doc.sire_animal:
		label = frappe.db.get_value("Animal", doc.sire_animal, "tag_number") or doc.sire_animal
	return {
		"sire_animal": doc.sire_animal or "",
		"sire_label": label or (doc.sire or ""),
		"sire_inferred": bool(doc.sire_inferred),
		"sire_basis": doc.sire_basis or inferred.get("basis") or "",
		"candidates": [
			{k: c[k] for k in ("animal", "label", "basis")} for c in inferred.get("candidates", [])
		],
		"conception_date": str(doc.conception_date or ""),
		"service_type": doc.service_type,
	}


def ensure_pregnancy_for_calving(calving):
	"""A calving with no confirmed pregnancy on file: create the Natural Service
	and its confirmation, link the calving to it. Returns the service name.

	Conception is the calving date minus the gestation period; the diagnosis is
	dated the usual number of days after it (never after the calving).
	"""
	from upande_livestock.serverscripts.common.events import new_livestock_event

	conception = add_days(getdate(calving.event_date), -get_timing("gestation_period_days"))
	service = create_natural_service(
		calving.animal, conception, operator=calving.operator,
		remarks="Derived from the calving on {0}".format(frappe.utils.formatdate(calving.event_date)))
	checked = min(
		add_days(conception, get_timing("pregnancy_check_days_after_service")), getdate(calving.event_date))
	dx = new_livestock_event(
		{"animal": calving.animal, "operator": calving.operator, "event_date": str(checked),
		 "remarks": "Derived from the calving on {0}".format(frappe.utils.formatdate(calving.event_date))},
		"Pregnancy Diagnosis", date_key="diagnosis_date", derived=True)
	dx.diagnosis_date = dx.event_date
	dx.diagnosis_result = "Confirmed"
	dx.related_service = service.name
	dx.insert()
	dx.submit()
	calving.flags.derived_docs = {"service": service.name, "pregnancy_diagnosis": dx.name}
	return service.name
