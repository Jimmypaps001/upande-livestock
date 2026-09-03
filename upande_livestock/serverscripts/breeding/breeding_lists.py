"""The two breeding worklists: pregnancy checks due, and animals ready to serve.

The single answer to both questions. api/reproduction.py once carried a second,
independent implementation that disagreed — 8 animals ready against 2 — because
it sidestepped a corrupted `custom_related_pregnancy` rather than being subject
to it, while itself ignoring Animal status, hardcoding a 60-day wait over the
configured ready_for_service_date, and returning a row per calving instead of
per animal. The corruption is fixed at its source and repaired in history; the
duplicate is gone. Read-guarded on Livestock Event."""

import frappe
from frappe.utils import today

from upande_livestock.serverscripts.common.choices import animal_label, herd_label_map
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run


@frappe.whitelist()
def breeding_lists():
	"""Supporting worklists: pending pregnancy checks and animals ready to serve."""

	def go():
		guard_read("Livestock Event")
		labels = herd_label_map()
		# Pregnancy checks due: submitted Service events still pending, whose
		# 35-day check window has arrived.
		due = frappe.db.sql(
			"""SELECT name, animal, current_herd, service_date, pregnancy_check_due_date
			   FROM `tabLivestock Event`
			   WHERE event_type = 'Service' AND docstatus = 1
			     AND pregnancy_confirmation_status = 'Pending'
			     AND IFNULL(pregnancy_check_due_date, service_date) <= %s
			   ORDER BY pregnancy_check_due_date ASC LIMIT 200""",
			(today(),),
			as_dict=True,
		)
		# Ready for service: active, not currently confirmed-pregnant, no pending
		# service, and past the post-partum window (ready_for_service_date on the
		# last calving, else nothing pending).
		ready = frappe.db.sql(
			"""SELECT a.name, a.tag_number, a.burn_name, a.current_herd, a.repro_status
			   FROM `tabAnimal` a
			   WHERE IFNULL(a.status,'') NOT IN ('Dead','Deceased','Sold','Culled','Disposed')
			     AND NOT EXISTS (
			       SELECT 1 FROM `tabLivestock Event` s
			       WHERE s.animal = a.name AND s.event_type='Service' AND s.docstatus=1
			         AND s.pregnancy_confirmation_status IN ('Pending','Confirmed')
			         AND NOT EXISTS (
			           SELECT 1 FROM `tabLivestock Event` c
			           WHERE c.animal=s.animal AND c.event_type='Calving'
			             AND c.custom_related_pregnancy=s.name AND c.docstatus=1))
			     AND EXISTS (
			       SELECT 1 FROM `tabLivestock Event` cal
			       WHERE cal.animal=a.name AND cal.event_type='Calving' AND cal.docstatus=1
			         AND IFNULL(cal.ready_for_service_date, cal.event_date) <= %s)
			   ORDER BY a.tag_number ASC LIMIT 200""",
			(today(),),
			as_dict=True,
		)
		return {
			"ok": True,
			"pregnancy_checks": [
				{
					"service": r.name,
					"animal": r.animal,
					"herd_label": labels.get(r.current_herd or "", r.current_herd or ""),
					"service_date": str(r.service_date) if r.service_date else "",
					"due": str(r.pregnancy_check_due_date) if r.pregnancy_check_due_date else "",
				}
				for r in due
			],
			"ready_for_service": [
				{
					"animal": r.name,
					"label": animal_label(r),
					"herd_label": labels.get(r.current_herd or "", r.current_herd or ""),
				}
				for r in ready
			],
		}

	return run(go, "livestock breeding_lists failed")
