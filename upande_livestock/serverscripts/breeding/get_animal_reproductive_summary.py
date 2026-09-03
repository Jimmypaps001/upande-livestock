"""One animal's reproductive history: last service, pending checks, conception rate.

Per-animal, so it is not the herd-wide worklist — that is breeding_lists,
and this module once carried a duplicate of it that disagreed. Read-guarded
on Livestock Event."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read


@frappe.whitelist()
def get_animal_reproductive_summary(animal=None):
	guard_read("Livestock Event")
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
