"""Scheduled livestock reproductive-alert tasks, ported from a sandboxed Frappe Scheduler Event Server Script.

The five ToDo sweeps below are unchanged. What is new is that the first of them
— the overdue pregnancy check, the one thing here that is genuinely late rather
than merely upcoming — now also raises a `Livestock Alert`, and that this task
delivers the open alerts at the end.

A ToDo and a notification are not the same thing and neither replaces the other:
a ToDo is a work item somebody is assigned and closes, a notification is how a
person finds out at all. The ToDos keep their audience (the serving operator);
the alert reaches the breeder, the vet and the manager, who may not be that
operator.
"""

import frappe

from upande_livestock.serverscripts.alerts import raise_alerts as herd_alerts
from upande_livestock.serverscripts.common import herd_movement, notifications

#: Days after a service by which a diagnosis should have been recorded, when
#: Livestock Settings has no `pregnancy_check_days_after_service`. Sixty is the
#: number the SQL below has always hardcoded, so an unset field changes nothing.
DEFAULT_PREGNANCY_CHECK_DAYS = 60


def pregnancy_check_days():
	configured = herd_movement.settings().get("pregnancy_check_days_after_service")
	return int(configured or 0) or DEFAULT_PREGNANCY_CHECK_DAYS


def raise_pregnancy_check_alerts():
	"""Record a `Pregnancy Check Overdue` alert per service still undiagnosed.

	Deliberately NOT reusing the ToDo query above it. That one excludes anything
	that already has a ToDo raised today, which is the right dedupe for a ToDo
	and the wrong one for an alert: an alert is deduplicated on whether one is
	still open (`herd_alerts.already_open`), so that a check overdue for a month
	is one row and one notification rather than thirty of each.
	"""
	due_after = pregnancy_check_days()
	overdue = frappe.db.sql(
		"""
		SELECT e.name AS service, e.animal, e.service_date,
		       a.tag_number, a.burn_name, a.current_herd,
		       DATEDIFF(CURDATE(), e.service_date) AS days_since
		FROM `tabLivestock Event` e
		JOIN `tabAnimal` a ON a.name = e.animal
		WHERE e.event_type = 'Service'
		  AND e.pregnancy_confirmation_status = 'Pending'
		  AND e.docstatus = 1
		  AND DATEDIFF(CURDATE(), e.service_date) > %(due)s
		  AND IFNULL(a.disabled, 0) = 0
		  AND a.status NOT IN ('Dead', 'Deceased', 'Sold', 'Culled', 'Disposed')
		""",
		{"due": due_after},
		as_dict=True,
	)

	raised = 0
	for r in overdue:
		if herd_alerts.already_open("Pregnancy Check Overdue", r.animal):
			continue
		label = r.tag_number or r.burn_name or r.animal
		days = int(r.days_since or 0)
		doc = frappe.new_doc("Livestock Alert")
		doc.alert_kind = "Pregnancy Check Overdue"
		doc.alert_date = frappe.utils.nowdate()
		doc.animal = r.animal
		doc.herd = r.current_herd
		doc.severity = "Overdue"
		doc.message = (
			f"{label} was served {days} days ago and still has no pregnancy diagnosis "
			f"— {days - due_after} days past the {due_after}-day check."
		)
		doc.detail = frappe.as_json({
			"service": r.service,
			"service_date": str(r.service_date),
			"days_since": days,
			"check_due_after_days": due_after,
		})
		doc.insert(ignore_permissions=True)
		raised += 1
	return raised


def check_overdue_pregnancy_diagnoses():
	# ============================================================
	# 1. CHECK OVERDUE PREGNANCY DIAGNOSES
	# ============================================================

	overdue_services = frappe.db.sql(
		"""
        SELECT
            ae.name,
            ae.animal,
            a.burn_name AS asset_name,
            a.current_herd AS custom_current_herd,
            ae.service_date,
            ae.operator,
            DATEDIFF(CURDATE(), ae.service_date) as days_since
        FROM `tabLivestock Event` ae
        LEFT JOIN `tabAnimal` a ON ae.animal = a.name
        WHERE ae.event_type = 'Service'
        AND ae.pregnancy_confirmation_status = 'Pending'
        AND ae.docstatus = 1
        AND DATEDIFF(CURDATE(), ae.service_date) > 60
        AND NOT EXISTS (
            SELECT 1 FROM `tabToDo` t
            WHERE t.reference_type = 'Livestock Event'
            AND t.reference_name = ae.name
            AND t.description LIKE '%Overdue%'
            AND t.status != 'Cancelled'
            AND DATE(t.creation) = CURDATE()
        )
    """,
		as_dict=True,
	)

	for service in overdue_services:
		todo = frappe.get_doc(
			{
				"doctype": "ToDo",
				"description": f"""<b>🚨 OVERDUE: Pregnancy Check Required</b><br><br>
                Animal: <b>{service.animal}</b> ({service.asset_name or ''})<br>
                Herd: <b>{service.custom_current_herd or 'Not assigned'}</b><br>
                Service Date: <b>{frappe.utils.formatdate(service.service_date)}</b><br>
                Days Overdue: <b>{service.days_since} days</b><br>
                Service Event: <b>{service.name}</b><br><br>
                <b>Action Required:</b> Record pregnancy diagnosis immediately!""",
				"reference_type": "Livestock Event",
				"reference_name": service.name,
				"priority": "High",
				"status": "Open",
				"date": frappe.utils.nowdate(),
			}
		)

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

	upcoming_calvings = frappe.db.sql(
		"""
        SELECT
            ae.name,
            ae.animal,
            a.burn_name AS asset_name,
            a.current_herd AS custom_current_herd,
            ae.service_date,
            DATE_ADD(ae.service_date, INTERVAL 280 DAY) as expected_calving,
            DATEDIFF(DATE_ADD(ae.service_date, INTERVAL 280 DAY), CURDATE()) as days_until
        FROM `tabLivestock Event` ae
        LEFT JOIN `tabAnimal` a ON ae.animal = a.name
        WHERE ae.event_type = 'Service'
        AND ae.pregnancy_confirmation_status = 'Confirmed'
        AND ae.docstatus = 1
        AND DATE_ADD(ae.service_date, INTERVAL 280 DAY)
            BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
        AND NOT EXISTS (
            SELECT 1 FROM `tabLivestock Event` c
            WHERE c.custom_related_pregnancy = ae.name
            AND c.event_type = 'Calving'
            AND c.docstatus = 1
        )
        AND NOT EXISTS (
            SELECT 1 FROM `tabToDo` t
            WHERE t.reference_type = 'Livestock Event'
            AND t.reference_name = ae.name
            AND t.description LIKE '%Calving Expected%'
            AND t.status != 'Cancelled'
            AND DATE(t.creation) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        )
    """,
		as_dict=True,
	)

	for calving in upcoming_calvings:
		urgency = "High" if calving.days_until <= 3 else "Medium"

		todo = frappe.get_doc(
			{
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
				"reference_type": "Livestock Event",
				"reference_name": calving.name,
				"priority": urgency,
				"status": "Open",
				"date": calving.expected_calving,
			}
		)

		todo.insert(ignore_permissions=True)

	frappe.db.commit()

	# ============================================================
	# 3. CHECK ANIMALS READY FOR RE-BREEDING (EXACTLY 60 DAYS)
	# ============================================================

	ready_animals = frappe.db.sql(
		"""
        SELECT
            ae.name,
            ae.animal,
            a.burn_name AS asset_name,
            a.current_herd AS custom_current_herd,
            ae.event_date as calving_date,
            DATEDIFF(CURDATE(), ae.event_date) as days_since_calving
        FROM `tabLivestock Event` ae
        LEFT JOIN `tabAnimal` a ON ae.animal = a.name
        WHERE ae.event_type = 'Calving'
        AND ae.docstatus = 1
        AND ae.custom_calving_outcome = 'Live Birth'
        AND DATEDIFF(CURDATE(), ae.event_date) = 60
        AND NOT EXISTS (
            SELECT 1 FROM `tabLivestock Event` s
            WHERE s.animal = ae.animal
            AND s.event_type = 'Service'
            AND s.service_date > ae.event_date
            AND s.pregnancy_confirmation_status = 'Confirmed'
            AND s.docstatus = 1
        )
    """,
		as_dict=True,
	)

	for animal in ready_animals:
		todo = frappe.get_doc(
			{
				"doctype": "ToDo",
				"description": f"""<b>✅ Animal Ready for Re-breeding!</b><br><br>
                Animal: <b>{animal.animal}</b> ({animal.asset_name or ''})<br>
                Herd: <b>{animal.custom_current_herd or 'Not assigned'}</b><br>
                Last Calving: <b>{frappe.utils.formatdate(animal.calving_date)}</b><br>
                Days Since Calving: <b>{animal.days_since_calving} days</b><br><br>
                <b>Action:</b> Watch for heat signs and service when detected.""",
				"reference_type": "Livestock Event",
				"reference_name": animal.name,
				"priority": "Medium",
				"status": "Open",
				"date": frappe.utils.nowdate(),
			}
		)

		todo.insert(ignore_permissions=True)

	frappe.db.commit()

	# ============================================================
	# 4. CHECK EXPECTED HEAT CYCLES (21 DAYS AFTER FAILED SERVICE)
	# ============================================================

	expected_heats = frappe.db.sql(
		"""
        SELECT
            ae.name,
            ae.animal,
            a.burn_name AS asset_name,
            a.current_herd AS custom_current_herd,
            ae.service_date,
            ae.pregnancy_confirmation_status,
            DATE_ADD(ae.service_date, INTERVAL 21 DAY) as expected_heat_date
        FROM `tabLivestock Event` ae
        LEFT JOIN `tabAnimal` a ON ae.animal = a.name
        WHERE ae.event_type = 'Service'
        AND ae.pregnancy_confirmation_status IN ('Not Pregnant', 'Aborted', 'Failed')
        AND ae.docstatus = 1
        AND DATE_ADD(ae.service_date, INTERVAL 21 DAY) = CURDATE()
        AND NOT EXISTS (
            SELECT 1 FROM `tabLivestock Event` s2
            WHERE s2.animal = ae.animal
            AND s2.event_type = 'Service'
            AND s2.service_date > ae.service_date
            AND s2.docstatus = 1
        )
    """,
		as_dict=True,
	)

	for heat in expected_heats:
		todo = frappe.get_doc(
			{
				"doctype": "ToDo",
				"description": f"""<b>🔥 Expected Heat Today!</b><br><br>
                Animal: <b>{heat.animal}</b> ({heat.asset_name or ''})<br>
                Herd: <b>{heat.custom_current_herd or 'Not assigned'}</b><br>
                Last Service: <b>{frappe.utils.formatdate(heat.service_date)}</b><br>
                Last Result: <b>{heat.pregnancy_confirmation_status}</b><br>
                Expected Heat: <b>Today (21-day cycle)</b><br><br>
                <b>Action:</b> Watch for heat signs and service if detected.""",
				"reference_type": "Livestock Event",
				"reference_name": heat.name,
				"priority": "Medium",
				"status": "Open",
				"date": frappe.utils.nowdate(),
			}
		)

		todo.insert(ignore_permissions=True)

	frappe.db.commit()

	# ============================================================
	# 5. IDENTIFY PROBLEM ANIMALS (REPEAT BREEDERS)
	# ============================================================

	repeat_breeders = frappe.db.sql(
		"""
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
            FROM `tabLivestock Event` ae
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
    """,
		as_dict=True,
	)

	for animal in repeat_breeders:
		todo = frappe.get_doc(
			{
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
				"date": frappe.utils.nowdate(),
			}
		)

		todo.insert(ignore_permissions=True)

	frappe.db.commit()

	# ============================================================
	# 6. RAISE AND DELIVER THE ALERTS THE ToDos ABOVE ONLY IMPLIED
	# ============================================================

	raised = raise_pregnancy_check_alerts()
	delivery = notifications.deliver_open_alerts()
	frappe.db.commit()

	# Log completion
	frappe.logger().info(
		f"Completed Daily Reproductive Alerts — {raised} alerts raised, "
		f"{delivery['delivered']} notifications delivered"
	)
