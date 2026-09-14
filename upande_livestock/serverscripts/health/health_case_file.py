# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One health case, whole: the file and everything written in it."""

import frappe
from frappe.utils import date_diff, flt, getdate

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.common.health_case import (
	TREATING_STATUSES,
	concern,
	concern_days,
	days_open,
	stale_days,
)

#: How a response reads as a direction, for drawing the course of the illness.
#: Not a score of how ill she is — a score of which way she is going, which is
#: the only thing a run of observations can honestly say.
RESPONSE_TREND = {
	"Worsening": -1,
	"No Change": 0,
	"Improving": 1,
	"Resolved": 2,
	"Not Yet Assessed": None,
}


@frappe.whitelist()
def health_case_file(payload=None):
	"""The file: who, what was wrong, what was given, and which way she went.

	READ, NOT EDITED. A case is a record of something that happened over days —
	it is not a form to be corrected afterwards. What can be added to it is a
	treatment, which is a new fact with its own date, and that goes through
	`treat_animal`. This endpoint is the reading.

	THE COURSE OF THE ILLNESS IS THE POINT. A list of five treatments tells you
	drugs were given. The same five with their dates and the response recorded
	against each tells you whether she was getting better — which is the
	question the file exists to answer and the one nobody could answer from the
	old screen, because the response column was on the doctype and on no page.

	Day numbers come with every entry. "Day 4" is how a course is read; the
	calendar date is how it is filed, and both are needed for different reasons.
	"""

	def go():
		guard_read("Livestock Health Case")
		d = as_dict(payload) if payload else {}
		name = (d.get("case") or "").strip()
		if not name:
			frappe.throw(frappe._("Select a case."))
		if not frappe.db.exists("Livestock Health Case", name):
			frappe.throw(frappe._("There is no case called {0}.").format(name))

		doc = frappe.get_doc("Livestock Health Case", name)
		opened = getdate(doc.opened_date) if doc.opened_date else None

		entries = []
		drugs = {}
		for row in sorted(
			doc.treatments or [],
			key=lambda t: (str(t.treatment_date or ""), t.idx or 0),
		):
			on = getdate(row.treatment_date) if row.treatment_date else None
			entries.append({
				"name": row.name,
				"on": str(on) if on else None,
				"day": (date_diff(on, opened) + 1) if (on and opened) else None,
				"time": str(row.treatment_time) if row.treatment_time else None,
				"drug": row.drug_item or row.drug_name_text or None,
				"drug_item": row.drug_item or None,
				"qty": flt(row.qty),
				"dosage": row.dosage,
				"route": row.route,
				"withdrawal_days": row.withdrawal_period_days,
				"by": row.administered_by,
				"response": row.response_observed or None,
				"trend": RESPONSE_TREND.get(row.response_observed),
				"cost": flt(row.cost),
				"issued": row.stock_entry_ref or None,
				"notes": row.notes,
			})
			key = row.drug_item or row.drug_name_text
			if key:
				held = drugs.setdefault(key, {"drug": key, "qty": 0.0, "times": 0, "uom": None})
				held["qty"] += flt(row.qty)
				held["times"] += 1

		for held in drugs.values():
			if frappe.db.exists("Item", held["drug"]):
				held["uom"] = frappe.db.get_value("Item", held["drug"], "stock_uom")

		case = {
			"name": doc.name,
			"animal": doc.animal,
			"animal_name": doc.animal_name or doc.animal,
			"herd": doc.current_herd,
			"case_status": doc.case_status,
			"open": doc.case_status in TREATING_STATUSES,
			"opened_date": str(doc.opened_date) if doc.opened_date else None,
			"closed_date": str(doc.closed_date) if doc.closed_date else None,
			"opened_by": doc.opened_by,
			"presenting_symptoms": doc.presenting_symptoms,
			"body_systems": doc.body_systems,
			"provisional_diagnosis": doc.provisional_diagnosis,
			"confirmed_diagnosis": doc.confirmed_diagnosis,
			"severity": doc.severity,
			"vet_called": bool(doc.vet_called),
			"vet_name": doc.vet_name,
			"vet_visit_date": str(doc.vet_visit_date) if doc.vet_visit_date else None,
			"milk_safe_date": str(doc.milk_safe_date) if doc.milk_safe_date else None,
			"production_loss_kg": flt(doc.production_loss_kg),
			"treatment_cost": flt(doc.total_treatment_cost),
			"outcome_notes": doc.outcome_notes,
			"linked_disposal": doc.linked_disposal,
		}
		case["days_open"] = days_open(case)
		last_on = entries[-1]["on"] if entries else None
		case["concern"] = concern(case, last_on)

		return {
			"ok": True,
			"case": case,
			"entries": entries,
			"drugs": sorted(drugs.values(), key=lambda r: -r["qty"]),
			"verdict": _verdict(entries, case),
			"concern_days": concern_days(),
			"stale_days": stale_days(),
			# Her other files, so a repeat is visible from inside the one you
			# are reading rather than only from the register.
			"others": frappe.get_all(
				"Livestock Health Case",
				filters={"animal": doc.animal, "docstatus": 1, "name": ["!=", doc.name]},
				fields=["name", "opened_date", "closed_date", "case_status",
				        "provisional_diagnosis"],
				order_by="opened_date desc",
				limit_page_length=8,
			),
		}

	return run(go, "livestock health_case_file failed")


def _verdict(entries, case):
	"""Which way she went, in one sentence, from what was actually recorded.

	SILENT WHERE THE RECORD IS SILENT. A course with no responses written
	against it cannot say whether she improved, and saying so is the honest
	answer — inferring "improving" from the fact that treatment stopped would
	read a recovery into a file that was simply abandoned.
	"""
	scored = [e for e in entries if e["trend"] is not None]
	if not entries:
		return {"reads": "none", "says": frappe._("Nothing has been recorded against this file yet.")}
	if not scored:
		return {
			"reads": "unsaid",
			"says": frappe._(
				"{0} treatments recorded, none with a response against them — the file "
				"cannot say whether she got better."
			).format(len(entries)),
		}
	first, last = scored[0], scored[-1]
	if case.get("case_status") == "Recovered":
		return {"reads": "recovered", "says": frappe._("She recovered.")}
	if case.get("case_status") in ("Died", "Culled"):
		return {"reads": "lost", "says": frappe._("She did not recover.")}
	if last["trend"] > first["trend"]:
		return {"reads": "better", "says": frappe._("Improving since treatment started.")}
	if last["trend"] < first["trend"]:
		return {"reads": "worse", "says": frappe._("Worse than when treatment started.")}
	return {"reads": "same", "says": frappe._("No change recorded since treatment started.")}
