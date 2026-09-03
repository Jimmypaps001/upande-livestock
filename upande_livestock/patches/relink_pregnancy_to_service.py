# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Repoint Calving/Abortion pregnancy links from a Diagnosis to its Service.

`Livestock Event.custom_related_pregnancy` is read everywhere as a Service:
breeding_lists' ready-for-service query (api/operations.py), the overdue
pregnancy-check scheduler (tasks.py), the "not already calved" guard and the
Abortion auto-link (livestock_event.py), and the gestation-length check, which
reads `service_date` off whatever it names.

The controller's auto-resolvers always pick a Service, but only run when the
field is blank. `record_calf_births()` and `create_abortion_event()` set it
straight from a client-supplied `related_pregnancy`, and the clients sent
Pregnancy Diagnosis names. On the Kaitet site that left 10 of 14 submitted
Calvings pointing at a Diagnosis and none at a Service.

Because a Diagnosis has no `service_date`, none of those readers error — they
just match nothing. A served cow's Service never closes, so she is never listed
as ready to serve again, and the gestation warnings never fire.

A Diagnosis carries `related_service`, so this is a lookup rather than a guess.
Rows that cannot be resolved keep their existing value and are logged: blanking
would destroy the only remaining evidence of what they meant.

Idempotent. Runs after `_validate_pregnancy_link` starts rejecting new writes,
so it repairs history rather than racing the source of the corruption.
"""

import frappe

LINKED_TYPES = ("Calving", "Abortion")


def _mislinked_rows():
	"""Events whose pregnancy link names something other than a Service."""
	return frappe.db.sql(
		"""
		SELECT e.name, e.animal, e.event_type, e.custom_related_pregnancy AS points_at,
		       p.event_type AS points_at_type, p.animal AS points_at_animal,
		       p.related_service AS resolves_to
		FROM `tabLivestock Event` e
		JOIN `tabLivestock Event` p ON p.name = e.custom_related_pregnancy
		WHERE e.event_type IN %(types)s
		  AND IFNULL(e.custom_related_pregnancy, '') != ''
		  AND p.event_type != 'Service'
		""",
		{"types": LINKED_TYPES},
		as_dict=True,
	)


def execute():
	if not frappe.db.has_column("Livestock Event", "custom_related_pregnancy"):
		return

	repaired, skipped = 0, []
	for row in _mislinked_rows():
		service = frappe.db.get_value(
			"Livestock Event", row.resolves_to, ["name", "event_type", "animal"], as_dict=True
		) if row.resolves_to else None

		if not service or service.event_type != "Service" or service.animal != row.animal:
			skipped.append(
				f"{row.name} ({row.event_type}) -> {row.points_at} "
				f"[{row.points_at_type}]: no Service to resolve to"
			)
			continue

		# set_value, not doc.save(): every one of these is submitted, and the
		# repair must not re-run validate() on historical rows that may fail it
		# for unrelated reasons.
		frappe.db.set_value(
			"Livestock Event", row.name, "custom_related_pregnancy", service.name,
			update_modified=False,
		)
		repaired += 1

	if repaired or skipped:
		frappe.db.commit()

	print(f"[relink-pregnancy] repointed {repaired} event(s) to their Service")
	for line in skipped:
		print(f"[relink-pregnancy] SKIPPED {line}")
