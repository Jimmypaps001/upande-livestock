# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Mark the services whose pregnancy checks came back and were never written down.

WHY THERE IS ANYTHING TO REPAIR. `LivestockEvent.settle_related_service` — the
code that writes a check's result onto the service that asked for it — used to
live in `before_insert`. The service a diagnosis answers is auto-linked in
`validate()` when the caller does not name one, and validate runs AFTER
before_insert, so `related_service` was still empty every time the block asked
for it. It never ran.

What that cost is not a tidy-up. `carrying_animals()` reads the SERVICE, not the
diagnosis — so does the dry-off list, the calving list, and the feed forecast's
whole calving schedule. A farm with thirty-four confirmed pregnancies read as a
farm with none, and the screens that should have been offering cows to dry off
and cows about to calve offered nobody at all.

WHAT THIS WILL AND WILL NOT DO. Where a diagnosis names its service, the result
is written onto it. Where it names none, the service is inferred only when the
answer is unambiguous: exactly one submitted service for that animal on or
before the diagnosis, with nothing since that would have ended the pregnancy.
Anything less clear is LEFT ALONE and counted in the log — a patch that guessed
here would invent pregnancies, and an invented pregnancy buys feed for a calf
that does not exist.
"""

import frappe

#: Set alongside the confirmation. The Select on this field is spelled
#: "Successfull" and db_set does not validate, so the typo is the valid value.
SERVICE_HELD = "Successfull"
SERVICE_FAILED = "Failed"

#: What each diagnosis result makes of the service that asked for it.
OUTCOMES = {
	"Confirmed": ("Confirmed", SERVICE_HELD),
	"Not Pregnant": ("Not Pregnant", SERVICE_FAILED),
	"Aborted": ("Aborted", SERVICE_FAILED),
}


def execute():
	diagnoses = frappe.db.sql(
		"""SELECT name, animal, diagnosis_date, diagnosis_result, related_service
		   FROM `tabLivestock Event`
		   WHERE event_type = 'Pregnancy Diagnosis' AND docstatus = 1
		     AND IFNULL(diagnosis_result, '') != ''
		   ORDER BY diagnosis_date ASC, creation ASC""",
		as_dict=True,
	)

	settled, linked, already, ambiguous = 0, 0, 0, 0
	for d in diagnoses:
		service = d.related_service or _only_candidate(d)
		if not service:
			ambiguous += 1
			continue
		if not d.related_service:
			frappe.db.set_value(
				"Livestock Event", d.name, "related_service", service, update_modified=False
			)
			linked += 1

		status, service_status = OUTCOMES[d.diagnosis_result]
		current = frappe.db.get_value("Livestock Event", service, "pregnancy_confirmation_status")
		if current == status:
			already += 1
			continue
		# A later event may already have moved this service on — a calving closes
		# a pregnancy, an abortion marks it Aborted. Replaying an old Confirmed
		# over that would reopen a pregnancy the farm has already finished with.
		if current in ("Aborted", "Not Pregnant") and d.diagnosis_result == "Confirmed":
			ambiguous += 1
			continue

		frappe.db.set_value(
			"Livestock Event", service,
			{
				"pregnancy_confirmation_status": status,
				"service_status": service_status,
				"pregnancy_confirmation_date": d.diagnosis_date,
			},
			update_modified=False,
		)
		settled += 1

	frappe.db.commit()
	frappe.log_error(
		title="Livestock: services settled from their diagnoses",
		message=(
			f"{len(diagnoses)} submitted diagnoses read.\n"
			f"{settled} services marked from their check.\n"
			f"{linked} diagnoses linked to the service they answered.\n"
			f"{already} already agreed.\n"
			f"{ambiguous} left alone — no single unambiguous service, or the "
			f"service has since moved on."
		),
	)


def _only_candidate(d):
	"""The one service this diagnosis can be answering, or None if it is a guess.

	One submitted service, on or before the check, with no calving or abortion
	between the two. Two candidates is not a near-miss to be broken by recency —
	it is the farm having served her twice, and picking one would attach the
	check to the wrong pregnancy and date her calving from the wrong day.
	"""
	rows = frappe.db.sql(
		"""SELECT s.name
		   FROM `tabLivestock Event` s
		   WHERE s.animal = %(animal)s AND s.event_type = 'Service' AND s.docstatus = 1
		     AND s.service_date <= %(on)s
		     AND NOT EXISTS (
		       SELECT 1 FROM `tabLivestock Event` c
		       WHERE c.animal = s.animal AND c.docstatus = 1
		         AND c.event_type IN ('Calving', 'Abortion')
		         AND c.event_date >= s.service_date AND c.event_date <= %(on)s)
		   LIMIT 2""",
		{"animal": d.animal, "on": d.diagnosis_date},
		pluck="name",
	)
	return rows[0] if len(rows) == 1 else None
