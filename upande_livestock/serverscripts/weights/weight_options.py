"""What the weighing screen offers: animals, methods and the operator.

Read-guarded on Livestock Weight Record."""

import frappe

from upande_livestock.serverscripts.common.choices import (
	active_animals,
	animal_choices,
	herd_choices,
	herd_label_map,
	select_options,
)
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run


WEIGHBRIDGE = "Weighbridge"


@frappe.whitelist()
def weight_options(settings_only=0):
	def go():
		guard_read("Livestock Weight Record")
		labels = herd_label_map()
		methods = select_options("Livestock Weight Record", "method")
		# Settings decide what the farm can weigh with. An unticked weighbridge
		# is not offered; an unset default falls back to the first method left.
		# Read the raw row: an untouched site has none, and get_single_value would
		# report that as 0 and silently switch the weighbridge off.
		row = frappe.db.sql(
			"select value from tabSingles where doctype=%s and field=%s",
			("Livestock Settings", "weighbridge_available"),
		)
		bridge = row[0][0] if row else None
		if bridge not in (None, "") and not int(bridge):
			methods = [m for m in methods if m != WEIGHBRIDGE]
		default = frappe.db.get_single_value("Livestock Settings", "default_weight_method")
		# The phone keeps its own animal list and wants only the settings.
		slim = int(settings_only or 0)
		return {
			"ok": True,
			"animals": [] if slim else animal_choices(active_animals(), labels),
			# Weighing is a race through a crush as often as it is one cow on a
			# scale, so the screen can fill its list in from a herd.
			"herds": [] if slim else herd_choices(),
			"methods": methods,
			"default_method": default if default in methods else (methods[0] if methods else ""),
			"weighbridge_available": WEIGHBRIDGE in methods,
			"employee": current_employee(),
		}

	return run(go, "livestock weight_options failed")
