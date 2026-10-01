"""What the health screen offers: animals, diseases and the drugs in store.

Read-guarded on Livestock Health Case."""

import frappe

from upande_livestock.serverscripts.common import herd_movement
from upande_livestock.serverscripts.common.choices import (
	active_animals,
	animal_choices,
	herd_label_map,
	select_options,
)
from upande_livestock.serverscripts.common.company import default_company
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.event_items import consumes_items, items_for_event


@frappe.whitelist()
def health_options():
	def go():
		guard_read("Livestock Health Case")
		labels = herd_label_map()
		return {
			"ok": True,
			"animals": animal_choices(active_animals(), labels),
			# An abortion can only happen to a cow who was carrying. Offering
			# the whole herd invites a loss recorded against one who never was
			# — and there is then nothing for it to close.
			"carrying": animal_choices(
				[a for a in active_animals()
				 if a.name in {r["animal"] for r in herd_movement.carrying_animals()}],
				labels,
			),
			"diseases": [
				r.name
				for r in frappe.get_all(
					"Livestock Disease", fields=["name"], order_by="name asc", limit_page_length=500
				)
			],
			"abortion_causes": select_options("Livestock Event", "abortion_cause"),
			"appearances": select_options("Livestock Diagnosis", "appearance"),
			"hydrations": select_options("Livestock Diagnosis", "hydration"),
			"actions": select_options("Livestock Diagnosis", "action_taken"),
			"case_statuses": select_options("Livestock Health Case", "case_status"),
			"severities": select_options("Livestock Health Case", "severity"),
			# A treatment row is refused outright if its route is not one of
			# these, so the form has to be able to offer them rather than let
			# the operator type "Oral" and lose the whole case.
			"routes": select_options("Livestock Health Treatment", "route"),
			"responses": select_options("Livestock Health Treatment", "response_observed"),
			# What each of this screen's event types may use, by type. One
			# endpoint serves several screens, so a bare list could not say whose.
			# A type the farm mapped nothing to has NO key: absent means "not
			# configured, show nothing", while [] means "mapped, nothing in stock".
			"items_by_event": {t: items_for_event(t) for t in ('Abortion',) if consumes_items(t)},
			"employee": current_employee(),
			"company": default_company(),
		}

	return run(go, "livestock health_options failed")
