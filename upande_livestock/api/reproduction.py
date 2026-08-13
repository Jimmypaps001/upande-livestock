"""Reproduction API endpoints, ported from sandboxed Frappe Server Scripts."""

import frappe


@frappe.whitelist()
def get_animal_reproductive_summary(animal=None):
    if not animal:
        frappe.throw("Animal parameter is required")

    # Initialize summary
    summary = {}

    # Get current status from Asset
    asset = frappe.get_doc("Animal", animal)
    summary["current_status"] = (asset.get("repro_status") or "Unknown")
    summary["pregnancy_status"] = (asset.get("custom_pregnancy_status") or "Unknown")

    # Get last service
    last_service = frappe.db.sql("""
        SELECT name, service_date, service_type, pregnancy_confirmation_status,
               expected_calving_date
        FROM `tabLivestock Event`
        WHERE animal = %s
        AND event_type = 'Service'
        AND docstatus = 1
        ORDER BY service_date DESC
        LIMIT 1
    """, (animal,), as_dict=True)

    if last_service:
        summary["last_service"] = last_service[0]
        summary["days_since_service"] = frappe.utils.date_diff(frappe.utils.nowdate(), last_service[0].service_date)

    # Get pending checks
    pending_checks = frappe.db.sql("""
        SELECT name, service_date, pregnancy_check_due_date
        FROM `tabLivestock Event`
        WHERE animal = %s
        AND event_type = 'Service'
        AND pregnancy_confirmation_status = 'Pending'
        AND docstatus = 1
    """, (animal,), as_dict=True)

    summary["pending_checks"] = pending_checks

    # Get last calving
    last_calving = frappe.db.sql("""
        SELECT name, event_date, custom_calving_outcome
        FROM `tabLivestock Event`
        WHERE animal = %s
        AND event_type = 'Calving'
        AND docstatus = 1
        ORDER BY event_date DESC
        LIMIT 1
    """, (animal,), as_dict=True)

    if last_calving:
        summary["last_calving"] = last_calving[0]
        summary["days_since_calving"] = frappe.utils.date_diff(frappe.utils.nowdate(), last_calving[0].event_date)

    # Get service performance
    total_services = frappe.db.count("Livestock Event", {
        "animal": animal,
        "event_type": "Service",
        "docstatus": 1
    })

    successful_services = frappe.db.count("Livestock Event", {
        "animal": animal,
        "event_type": "Service",
        "service_status": "Successful",
        "docstatus": 1
    })

    summary["total_services"] = total_services
    summary["successful_services"] = successful_services
    summary["conception_rate"] = (successful_services / total_services * 100) if total_services > 0 else 0

    # Set response
    return summary


@frappe.whitelist()
def get_animals_ready_for_service():
    # Get animals ready for service
    ready_animals = frappe.db.sql("""
        SELECT
            ae.animal,
            a.burn_name AS asset_name,
            a.current_herd AS custom_current_herd,
            ae.event_date as calving_date,
            DATEDIFF(CURDATE(), ae.event_date) as days_since_calving,
            ae.ready_for_service_date
        FROM `tabLivestock Event` ae
        LEFT JOIN `tabAnimal` a ON ae.animal = a.name
        WHERE ae.event_type = 'Calving'
        AND ae.docstatus = 1
        AND DATEDIFF(CURDATE(), ae.event_date) >= 60
        AND NOT EXISTS (
            SELECT 1 FROM `tabLivestock Event` service
            WHERE service.animal = ae.animal
            AND service.event_type = 'Service'
            AND service.service_date > ae.event_date
            AND service.docstatus = 1
        )
        ORDER BY ae.event_date ASC
    """, as_dict=True)

    # Set response
    return ready_animals


@frappe.whitelist()
def get_animals_needing_pregnancy_check():
    # Get animals needing pregnancy check
    animals_needing_check = frappe.db.sql("""
        SELECT
            ae.animal,
            ae.name as service_event,
            ae.service_date,
            ae.pregnancy_check_due_date,
            DATEDIFF(CURDATE(), ae.service_date) as days_since_service,
            CASE
                WHEN DATEDIFF(CURDATE(), ae.pregnancy_check_due_date) > 20 THEN 'Overdue'
                WHEN DATEDIFF(CURDATE(), ae.pregnancy_check_due_date) > 0 THEN 'Due'
                ELSE 'Upcoming'
            END as urgency,
            a.burn_name AS asset_name,
            a.current_herd AS custom_current_herd
        FROM `tabLivestock Event` ae
        LEFT JOIN `tabAnimal` a ON ae.animal = a.name
        WHERE ae.event_type = 'Service'
        AND ae.pregnancy_confirmation_status = 'Pending'
        AND ae.docstatus = 1
        AND DATEDIFF(CURDATE(), ae.service_date) >= 21
        ORDER BY ae.pregnancy_check_due_date ASC
    """, as_dict=True)

    # Set response
    return animals_needing_check
