"""Per-animal reproductive history.

Held one endpoint per animal plus two herd-wide worklists — "ready for service"
and "pregnancy checks due". Both worklists were also implemented, independently,
in `operations.breeding_lists`, and the two disagreed: on kaitet.local this
module reported 8 animals ready to serve against breeding_lists' 2.

The gap was not a difference of opinion about breeding. `breeding_lists` filters
on `custom_related_pregnancy`, which had been corrupted to hold Pregnancy
Diagnosis names instead of Service names, so served cows never closed out. This
module happened to sidestep that by asking a different question ("no Service
since the last Calving") — while itself ignoring Animal status, hardcoding a
60-day wait instead of the Calving's configured `ready_for_service_date`, and
returning one row per calving rather than per animal.

The corruption is fixed at its source (`_validate_pregnancy_link`) and repaired
in history (`patches.relink_pregnancy_to_service`), so the duplicates are gone
and `operations.breeding_lists` is the single answer. See
`test_operations.TestOneSourceForBreedingWorklists`.
"""

import frappe


@frappe.whitelist()
def get_animal_reproductive_summary(animal=None):
	if not animal:
		frappe.throw("Animal parameter is required")

	# Initialize summary
	summary = {}

	# Get current status from Asset
	asset = frappe.get_doc("Animal", animal)
	summary["current_status"] = asset.get("repro_status") or "Unknown"
	summary["pregnancy_status"] = asset.get("custom_pregnancy_status") or "Unknown"

	# Get last service
	last_service = frappe.db.sql(
		"""
        SELECT name, service_date, service_type, pregnancy_confirmation_status,
               expected_calving_date
        FROM `tabLivestock Event`
        WHERE animal = %s
        AND event_type = 'Service'
        AND docstatus = 1
        ORDER BY service_date DESC
        LIMIT 1
    """,
		(animal,),
		as_dict=True,
	)

	if last_service:
		summary["last_service"] = last_service[0]
		summary["days_since_service"] = frappe.utils.date_diff(
			frappe.utils.nowdate(), last_service[0].service_date
		)

	# Get pending checks
	pending_checks = frappe.db.sql(
		"""
        SELECT name, service_date, pregnancy_check_due_date
        FROM `tabLivestock Event`
        WHERE animal = %s
        AND event_type = 'Service'
        AND pregnancy_confirmation_status = 'Pending'
        AND docstatus = 1
    """,
		(animal,),
		as_dict=True,
	)

	summary["pending_checks"] = pending_checks

	# Get last calving
	last_calving = frappe.db.sql(
		"""
        SELECT name, event_date, custom_calving_outcome
        FROM `tabLivestock Event`
        WHERE animal = %s
        AND event_type = 'Calving'
        AND docstatus = 1
        ORDER BY event_date DESC
        LIMIT 1
    """,
		(animal,),
		as_dict=True,
	)

	if last_calving:
		summary["last_calving"] = last_calving[0]
		summary["days_since_calving"] = frappe.utils.date_diff(
			frappe.utils.nowdate(), last_calving[0].event_date
		)

	# Get service performance
	total_services = frappe.db.count(
		"Livestock Event", {"animal": animal, "event_type": "Service", "docstatus": 1}
	)

	successful_services = frappe.db.count(
		"Livestock Event",
		{"animal": animal, "event_type": "Service", "service_status": "Successful", "docstatus": 1},
	)

	summary["total_services"] = total_services
	summary["successful_services"] = successful_services
	summary["conception_rate"] = (successful_services / total_services * 100) if total_services > 0 else 0

	# Set response
	return summary
