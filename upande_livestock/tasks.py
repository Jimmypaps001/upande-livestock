"""Scheduled livestock reproductive-alert tasks, ported from a sandboxed Frappe Scheduler Event Server Script."""

import frappe


def check_overdue_pregnancy_diagnoses():
    # ============================================================
    # 1. CHECK OVERDUE PREGNANCY DIAGNOSES
    # ============================================================

    overdue_services = frappe.db.sql("""
        SELECT
            ae.name,
            ae.animal,
            a.burn_name AS asset_name,
            a.current_herd AS custom_current_herd,
            ae.service_date,
            ae.operator,
            DATEDIFF(CURDATE(), ae.service_date) as days_since
        FROM `tabAnimal Event` ae
        LEFT JOIN `tabAnimal` a ON ae.animal = a.name
        WHERE ae.event_type = 'Service'
        AND ae.pregnancy_confirmation_status = 'Pending'
        AND ae.docstatus = 1
        AND DATEDIFF(CURDATE(), ae.service_date) > 60
        AND NOT EXISTS (
            SELECT 1 FROM `tabToDo` t
            WHERE t.reference_type = 'Animal Event'
            AND t.reference_name = ae.name
            AND t.description LIKE '%Overdue%'
            AND t.status != 'Cancelled'
            AND DATE(t.creation) = CURDATE()
        )
    """, as_dict=True)

    for service in overdue_services:
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "description": f"""<b>🚨 OVERDUE: Pregnancy Check Required</b><br><br>
                Animal: <b>{service.animal}</b> ({service.asset_name or ''})<br>
                Herd: <b>{service.custom_current_herd or 'Not assigned'}</b><br>
                Service Date: <b>{frappe.utils.formatdate(service.service_date)}</b><br>
                Days Overdue: <b>{service.days_since} days</b><br>
                Service Event: <b>{service.name}</b><br><br>
                <b>Action Required:</b> Record pregnancy diagnosis immediately!""",
            "reference_type": "Animal Event",
            "reference_name": service.name,
            "priority": "High",
            "status": "Open",
            "date": frappe.utils.nowdate()
        })

        # Assign to operator if exists
        if service.operator:
            operator_user = frappe.db.get_value("Employee", service.operator, "user_id")
            if operator_user:
                todo.allocated_to = operator_user

        todo.insert(ignore_permissions=True)

    frappe.db.commit()

    # ============================================================
    # 2. CHECK UPCOMING CALVINGS (NEXT 7 DAYS)
    # ============================================================

    upcoming_calvings = frappe.db.sql("""
        SELECT
            ae.name,
            ae.animal,
            a.burn_name AS asset_name,
            a.current_herd AS custom_current_herd,
            ae.service_date,
            DATE_ADD(ae.service_date, INTERVAL 280 DAY) as expected_calving,
            DATEDIFF(DATE_ADD(ae.service_date, INTERVAL 280 DAY), CURDATE()) as days_until
        FROM `tabAnimal Event` ae
        LEFT JOIN `tabAnimal` a ON ae.animal = a.name
        WHERE ae.event_type = 'Service'
        AND ae.pregnancy_confirmation_status = 'Confirmed'
        AND ae.docstatus = 1
        AND DATE_ADD(ae.service_date, INTERVAL 280 DAY)
            BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
        AND NOT EXISTS (
            SELECT 1 FROM `tabAnimal Event` c
            WHERE c.custom_related_pregnancy = ae.name
            AND c.event_type = 'Calving'
            AND c.docstatus = 1
        )
        AND NOT EXISTS (
            SELECT 1 FROM `tabToDo` t
            WHERE t.reference_type = 'Animal Event'
            AND t.reference_name = ae.name
            AND t.description LIKE '%Calving Expected%'
            AND t.status != 'Cancelled'
            AND DATE(t.creation) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        )
    """, as_dict=True)

    for calving in upcoming_calvings:
        urgency = "High" if calving.days_until <= 3 else "Medium"

        todo = frappe.get_doc({
            "doctype": "ToDo",
            "description": f"""<b>🐄 Calving Expected Soon!</b><br><br>
                Animal: <b>{calving.animal}</b> ({calving.asset_name or ''})<br>
                Herd: <b>{calving.custom_current_herd or 'Not assigned'}</b><br>
                Expected Date: <b>{frappe.utils.formatdate(calving.expected_calving)}</b><br>
                Days Until Calving: <b>{calving.days_until} days</b><br>
                Service Event: <b>{calving.name}</b><br><br>
                <b>Action Required:</b><br>
                • Prepare calving area<br>
                • Monitor animal closely<br>
                • Have calving kit ready""",
            "reference_type": "Animal Event",
            "reference_name": calving.name,
            "priority": urgency,
            "status": "Open",
            "date": calving.expected_calving
        })

        todo.insert(ignore_permissions=True)

    frappe.db.commit()

    # ============================================================
    # 3. CHECK ANIMALS READY FOR RE-BREEDING (EXACTLY 60 DAYS)
    # ============================================================

    ready_animals = frappe.db.sql("""
        SELECT
            ae.name,
            ae.animal,
            a.burn_name AS asset_name,
            a.current_herd AS custom_current_herd,
            ae.event_date as calving_date,
            DATEDIFF(CURDATE(), ae.event_date) as days_since_calving
        FROM `tabAnimal Event` ae
        LEFT JOIN `tabAnimal` a ON ae.animal = a.name
        WHERE ae.event_type = 'Calving'
        AND ae.docstatus = 1
        AND ae.custom_calving_outcome = 'Live Birth'
        AND DATEDIFF(CURDATE(), ae.event_date) = 60
        AND NOT EXISTS (
            SELECT 1 FROM `tabAnimal Event` s
            WHERE s.animal = ae.animal
            AND s.event_type = 'Service'
            AND s.service_date > ae.event_date
            AND s.pregnancy_confirmation_status = 'Confirmed'
            AND s.docstatus = 1
        )
    """, as_dict=True)

    for animal in ready_animals:
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "description": f"""<b>✅ Animal Ready for Re-breeding!</b><br><br>
                Animal: <b>{animal.animal}</b> ({animal.asset_name or ''})<br>
                Herd: <b>{animal.custom_current_herd or 'Not assigned'}</b><br>
                Last Calving: <b>{frappe.utils.formatdate(animal.calving_date)}</b><br>
                Days Since Calving: <b>{animal.days_since_calving} days</b><br><br>
                <b>Action:</b> Watch for heat signs and service when detected.""",
            "reference_type": "Animal Event",
            "reference_name": animal.name,
            "priority": "Medium",
            "status": "Open",
            "date": frappe.utils.nowdate()
        })

        todo.insert(ignore_permissions=True)

    frappe.db.commit()

    # ============================================================
    # 4. CHECK EXPECTED HEAT CYCLES (21 DAYS AFTER FAILED SERVICE)
    # ============================================================

    expected_heats = frappe.db.sql("""
        SELECT
            ae.name,
            ae.animal,
            a.burn_name AS asset_name,
            a.current_herd AS custom_current_herd,
            ae.service_date,
            ae.pregnancy_confirmation_status,
            DATE_ADD(ae.service_date, INTERVAL 21 DAY) as expected_heat_date
        FROM `tabAnimal Event` ae
        LEFT JOIN `tabAnimal` a ON ae.animal = a.name
        WHERE ae.event_type = 'Service'
        AND ae.pregnancy_confirmation_status IN ('Not Pregnant', 'Aborted', 'Failed')
        AND ae.docstatus = 1
        AND DATE_ADD(ae.service_date, INTERVAL 21 DAY) = CURDATE()
        AND NOT EXISTS (
            SELECT 1 FROM `tabAnimal Event` s2
            WHERE s2.animal = ae.animal
            AND s2.event_type = 'Service'
            AND s2.service_date > ae.service_date
            AND s2.docstatus = 1
        )
    """, as_dict=True)

    for heat in expected_heats:
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "description": f"""<b>🔥 Expected Heat Today!</b><br><br>
                Animal: <b>{heat.animal}</b> ({heat.asset_name or ''})<br>
                Herd: <b>{heat.custom_current_herd or 'Not assigned'}</b><br>
                Last Service: <b>{frappe.utils.formatdate(heat.service_date)}</b><br>
                Last Result: <b>{heat.pregnancy_confirmation_status}</b><br>
                Expected Heat: <b>Today (21-day cycle)</b><br><br>
                <b>Action:</b> Watch for heat signs and service if detected.""",
            "reference_type": "Animal Event",
            "reference_name": heat.name,
            "priority": "Medium",
            "status": "Open",
            "date": frappe.utils.nowdate()
        })

        todo.insert(ignore_permissions=True)

    frappe.db.commit()

    # ============================================================
    # 5. IDENTIFY PROBLEM ANIMALS (REPEAT BREEDERS)
    # ============================================================

    repeat_breeders = frappe.db.sql("""
        SELECT
            animal,
            asset_name,
            service_count,
            last_service_date
        FROM (
            SELECT
                ae.animal,
                a.burn_name AS asset_name,
                a.current_herd AS custom_current_herd,
                COUNT(*) as service_count,
                MAX(ae.service_date) as last_service_date
            FROM `tabAnimal Event` ae
            LEFT JOIN `tabAnimal` a ON ae.animal = a.name
            WHERE ae.event_type = 'Service'
            AND ae.docstatus = 1
            GROUP BY ae.animal, a.burn_name, a.current_herd
            HAVING COUNT(*) >= 3
            AND SUM(CASE WHEN ae.pregnancy_confirmation_status = 'Confirmed' THEN 1 ELSE 0 END) = 0
        ) as repeat_breeders
        WHERE NOT EXISTS (
            SELECT 1 FROM `tabToDo` t
            WHERE t.reference_type = 'Animal'
            AND t.reference_name = repeat_breeders.animal
            AND t.description LIKE '%Repeat Breeder%'
            AND t.status != 'Cancelled'
            AND DATE(t.creation) >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        )
    """, as_dict=True)

    for animal in repeat_breeders:
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "description": f"""<b>⚠️ Problem Animal: Repeat Breeder</b><br><br>
                Animal: <b>{animal.animal}</b> ({animal.asset_name or ''})<br>
                Total Services: <b>{animal.service_count}</b><br>
                Successful Pregnancies: <b>0</b><br>
                Last Service: <b>{frappe.utils.formatdate(animal.last_service_date)}</b><br><br>
                <b>Action Required:</b><br>
                • Veterinary examination<br>
                • Check for reproductive issues<br>
                • Consider culling if problem persists""",
            "reference_type": "Animal",
            "reference_name": animal.animal,
            "priority": "High",
            "status": "Open",
            "date": frappe.utils.nowdate()
        })

        todo.insert(ignore_permissions=True)

    frappe.db.commit()

    # Log completion
    frappe.logger().info("Completed Daily Reproductive Alerts")
