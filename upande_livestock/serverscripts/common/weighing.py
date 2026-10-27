# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who is overdue for a weighing.

Herds ticked "weigh monthly" are weighed on a cycle: an animal is overdue once
it has gone more than `weighing_interval_days + weighing_grace_days` since its
last submitted weight. Both numbers come from Livestock Settings; a configured
grace of 0 means no slack.

An animal that has never been weighed is counted from when it entered its
current herd, so a newcomer is not flagged on its first day and a forgotten one
is not exempt forever.
"""

import frappe
from frappe.utils import date_diff, getdate, today

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.timings import get_timing


def weighing_limit_days():
	"""Days an animal may go unweighed: interval plus grace."""
	return get_timing("weighing_interval_days") + get_timing("weighing_grace_days")


def _entered_herd(animal, herd, acquisition_date, creation):
	"""When the animal arrived where it stands: its latest Movement into the
	herd, else its acquisition date, else when it was entered on the system."""
	moved = frappe.db.get_value(
		"Livestock Event",
		{"animal": animal, "event_type": "Movement", "new_herd": herd, "docstatus": 1},
		"event_date",
		order_by="event_date desc",
	)
	return moved or acquisition_date or getdate(creation)


def weighing_due(animal=None):
	"""Active animals in weigh-monthly herds that are past interval + grace.

	`animal` narrows the question to one animal (used when a weighing is saved).
	"""
	herds = frappe.get_all("Herds", filters={"weigh_monthly": 1}, pluck="name")
	if not herds:
		return []
	limit = weighing_limit_days()
	last = dict(frappe.db.sql(
		"""SELECT animal, MAX(weight_date) FROM `tabLivestock Weight Record`
		   WHERE docstatus = 1 GROUP BY animal"""
	))
	extra = [["name", "=", animal]] if animal else []
	animals = frappe.get_all(
		"Animal",
		filters=extra + [
			["current_herd", "in", herds],
			["status", "not in", list(RETIRED_STATUSES)],
			["disabled", "=", 0],
		],
		fields=["name", "tag_number", "burn_name", "current_herd", "acquisition_date", "creation"],
		limit=5000,
	)
	out = []
	for a in animals:
		last_date = last.get(a.name)
		since = last_date or _entered_herd(a.name, a.current_herd, a.acquisition_date, a.creation)
		days = date_diff(today(), getdate(since))
		if days <= limit:
			continue
		out.append({
			"animal": a.name,
			"label": a.tag_number or a.burn_name or a.name,
			"herd": a.current_herd,
			"last_weight_date": getdate(last_date) if last_date else None,
			"days_since": days,
			"overdue_by": days - limit,
		})
	out.sort(key=lambda r: -r["overdue_by"])
	return out
