# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A health case is a file, and the rules about opening and closing one.

THE HOSPITAL SHAPE. You do not walk into a hospital and add a file; you are
seen, and if you are treated a file is opened, and everything done to you goes
in it. Months later you come back and a new file is opened, because that is a
different illness. The farm works the same way and the app did not: a case was
a form anybody could fill in for any animal at any time, unattached to the
check-up that found the problem or the drug that was given for it.

So there is one door in. A case is opened because a check-up escalated to one,
or because somebody is about to treat an animal who has no open file. Nothing
else opens one, and the file itself is then read: what was given, on what day,
by whom, and whether she got better.

WHAT COUNTS AS OPEN IS A LIST, NOT A NEGATION. `case_status` has six values and
none of them is "Closed" — so the filter this package used, `case_status !=
'Closed'`, matched every case ever recorded and the treatment picker offered
files that were shut months ago. Open is Open or Under Treatment, named.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

from upande_livestock.serverscripts.common.timings import get_timing

#: A file still being written in.
TREATING_STATUSES = ("Open", "Under Treatment")

#: A file with the book closed on it, however it ended.
CLOSED_STATUSES = ("Recovered", "Chronic", "Died", "Culled")

#: The statuses that mean she recovered, for reading a run of cases.
GOOD_ENDINGS = ("Recovered",)

def concern_days():
	"""How long a case may stay open before the farm wants to know.

	Through `get_timing`, not `frappe.db.get_single_value`: that helper casts,
	so a field the farm has never touched reads back as 0 — and 0 here means
	"do not tell me". An unconfigured farm would have silently switched the
	check off, which is the one answer neither value should ever produce by
	accident.
	"""
	return get_timing("health_case_concern_days")


def stale_days():
	"""How long an open case may go with nothing written in it."""
	return get_timing("health_case_stale_days")


def open_case_for(animal):
	"""Her open file, if she has one. Newest first, though there should be one.

	Returns the row rather than the name, because every caller that wants to
	know whether she has a file also wants to say which one and since when.
	"""
	rows = frappe.get_all(
		"Livestock Health Case",
		filters={
			"animal": animal,
			"docstatus": 1,
			"case_status": ["in", TREATING_STATUSES],
		},
		fields=["name", "opened_date", "case_status", "presenting_symptoms",
		        "provisional_diagnosis", "severity"],
		order_by="opened_date desc, creation desc",
		limit_page_length=1,
	)
	return rows[0] if rows else None


def days_open(case):
	"""How long the file has been open — to its closing, or to today."""
	if not case.get("opened_date"):
		return None
	end = case.get("closed_date") or today()
	return max(date_diff(getdate(end), getdate(case["opened_date"])), 0)


def concern(case, last_treatment_on=None):
	"""What is worrying about this open file, in the farm's own words.

	Two different worries and they are not the same thing. A case open for a
	month is a cow who is not recovering. A case with nothing written in it for
	a week is a cow nobody is writing anything down about, which may mean she
	recovered and the file was never closed — and that is worth knowing too,
	because it is the reason a farm's open-case count stops meaning anything.
	"""
	if case.get("case_status") not in TREATING_STATUSES:
		return None
	days = days_open(case)
	limit = concern_days()
	if limit and days is not None and days >= limit:
		return {
			"kind": "long",
			"days": days,
			"says": _("Open {0} days — past the {1} this farm asks about.").format(days, limit),
		}
	quiet = stale_days()
	if quiet and last_treatment_on:
		silent = date_diff(getdate(today()), getdate(last_treatment_on))
		if silent >= quiet:
			return {
				"kind": "stale",
				"days": silent,
				"says": _("Nothing recorded for {0} days. Either she is not being treated "
				          "or the file was never closed.").format(silent),
			}
	if quiet and not last_treatment_on and days is not None and days >= quiet:
		return {
			"kind": "untreated",
			"days": days,
			"says": _("Open {0} days with no treatment recorded at all.").format(days),
		}
	return None


def open_file(d, opened_from=None):
	"""Open a case for an animal and submit it. Returns the document.

	`d` is the same shape `create_health_case` takes. This exists so the two
	ways a file is legitimately opened — a check-up that escalated, and a
	treatment given to an animal with no open file — go through one piece of
	code rather than two that drift.
	"""
	from upande_livestock.serverscripts.common import backdate
	from upande_livestock.serverscripts.common.company import company_or_throw
	from upande_livestock.serverscripts.common.employee import current_employee

	animal = (d.get("animal") or "").strip()
	if not animal:
		frappe.throw(_("Select an animal."))
	symptoms = (d.get("presenting_symptoms") or "").strip()
	if not symptoms:
		frappe.throw(
			_("Say what is wrong with her. A file with no complaint on the front of it "
			  "is one nobody can treat from.")
		)

	doc = frappe.new_doc("Livestock Health Case")
	doc.animal = animal
	doc.company = company_or_throw(d.get("company"))
	opened_date, is_backdated = backdate.resolve(d, "opened_date")
	backdate.assert_allowed(is_backdated)
	doc.opened_date = opened_date
	backdate.stamp(doc, is_backdated)
	# A FILE HAS SOMEBODY'S NAME ON THE FRONT OF IT, and not only for the record:
	# LivestockHealthCase.post_drug_issue raises the Stock Entry in the name of
	# `opened_by`, so a file opened by nobody is a file no drug can ever be
	# issued against. It failed at the second treatment, long after the person
	# who could have answered had walked away.
	doc.opened_by = d.get("opened_by") or d.get("operator") or current_employee()
	if not doc.opened_by:
		frappe.throw(
			_("Say who is opening this file. Drugs are issued in that person's name, "
			  "so a file with nobody on it cannot be treated from.")
		)
	doc.case_status = d.get("case_status") or "Open"
	doc.presenting_symptoms = symptoms
	doc.body_systems = d.get("body_systems")
	doc.provisional_diagnosis = d.get("provisional_diagnosis") or None
	doc.severity = d.get("severity") or None
	doc.vet_called = 1 if d.get("vet_called") else 0
	doc.vet_name = d.get("vet_name")
	if opened_from:
		doc.outcome_notes = _("Opened from {0}.").format(opened_from)
	doc.insert()
	doc.submit()
	doc.reload()
	return doc


def treatment_row(t, fallback_date=None):
	"""One treatment as the child table wants it. Quantities are as issued."""
	from frappe.utils import flt

	from upande_livestock.serverscripts.common.employee import current_employee

	return {
		"treatment_date": t.get("treatment_date") or fallback_date or today(),
		"drug_item": t.get("drug_item") or None,
		"drug_name_text": t.get("drug_name_text"),
		"dosage": t.get("dosage"),
		"qty": flt(t.get("qty")) or 1,
		"route": t.get("route") or None,
		"withdrawal_period_days": int(flt(t.get("withdrawal_period_days"))) or None,
		"administered_by": t.get("administered_by") or current_employee(),
		"response_observed": t.get("response_observed") or None,
		"notes": t.get("notes"),
	}
