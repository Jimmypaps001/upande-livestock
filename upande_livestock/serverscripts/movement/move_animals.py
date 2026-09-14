# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Move a set of animals into one herd, in one go."""

import frappe
from frappe import _
from frappe.utils import today

from upande_livestock.serverscripts.common.animal import recompute_herd_count
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event


@frappe.whitelist()
def move_animals(payload):
	"""Walk several animals into `new_herd`, one Movement event each.

	ONE EVENT PER ANIMAL, not one for the batch. Her timeline has to be able to
	answer where she was in March on its own; a single record naming forty cows
	answers it for none of them, and the head counts would then have to be
	worked out by hand instead of falling out of the processor.

	THE WHOLE SET IS CHECKED BEFORE ANY OF IT MOVES. Forty animals picked off a
	list is forty chances for one to have left the farm since the page loaded,
	and a batch that moved thirty-nine and stopped would leave somebody
	reconciling which. Everything wrong is named at once, and nothing moves
	until none of it is.
	"""

	def go():
		guard("Livestock Event")
		d = as_dict(payload)
		herd = (d.get("new_herd") or "").strip()
		animals = [a for a in (d.get("animals") or []) if a]

		if not herd:
			frappe.throw(_("Choose the herd they are moving to."))
		if not frappe.db.exists("Herds", herd):
			frappe.throw(_("{0} is not a herd on this farm.").format(herd))
		if not animals:
			frappe.throw(_("Pick at least one animal."))

		problems, seen = [], set()
		for animal in animals:
			if animal in seen:
				problems.append(_("{0} is on the list twice.").format(animal))
				continue
			seen.add(animal)
			row = frappe.db.get_value(
				"Animal", animal, ["disabled", "status", "current_herd"], as_dict=True)
			if not row:
				problems.append(_("{0} is not an animal on this farm.").format(animal))
			elif row.disabled:
				problems.append(
					_("{0} has left the farm ({1}).").format(animal, (row.status or "").lower()))
			elif row.current_herd == herd:
				problems.append(_("{0} is already in {1}.").format(animal, herd))
		if problems:
			frappe.throw("\n".join(problems))

		when = d.get("event_date") or today()
		moved, from_herds = [], set()
		for animal in seen:
			was = frappe.db.get_value("Animal", animal, "current_herd")
			event = new_livestock_event(
				{"animal": animal, "operator": d.get("operator"), "event_date": when,
				 "remarks": d.get("remarks")},
				"Movement",
			)
			event.new_herd = herd
			event.current_herd = was or ""
			event.insert()
			event.submit()
			moved.append({"animal": animal, "from_herd": was, "event": event.name})
			if was:
				from_herds.add(was)

		for old in from_herds:
			recompute_herd_count(old)
		recompute_herd_count(herd)

		return {
			"ok": True,
			"herd": herd,
			"moved": moved,
			"count": len(moved),
			"heads": frappe.db.get_value("Herds", herd, "number_of_animals"),
			"emptied_from": sorted(from_herds),
		}

	return run(go, "livestock move_animals failed")
