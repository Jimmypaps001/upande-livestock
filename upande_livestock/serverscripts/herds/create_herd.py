# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Start a new herd from animals already on the farm."""

import frappe
from frappe import _
from frappe.utils import today

from upande_livestock.serverscripts.common.animal import recompute_herd_count
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event
from upande_livestock.serverscripts.feeding._standing_ration import set_standing_ration


@frappe.whitelist()
def create_herd(payload):
	"""Create a herd and walk animals into it.

	EVERY ANIMAL ARRIVES BY A MOVEMENT EVENT, never by writing `current_herd`.
	The herd a cow stands in is the answer to a question her timeline has to be
	able to answer — "where was she in March, and who moved her" — and a direct
	write leaves a herd full of animals that were never seen to arrive. It also
	keeps both head counts right without this function doing the arithmetic,
	because the movement processor already does.

	A ration is optional here. Splitting a herd on Monday and deciding what it
	eats on Tuesday is ordinary; refusing to create the herd until somebody has
	the formulation to hand would only mean the split happens in a notebook.
	"""

	def go():
		guard("Herds")
		d = as_dict(payload)
		name = (d.get("herd_name") or "").strip()
		animals = [a for a in (d.get("animals") or []) if a]

		if not name:
			frappe.throw(_("Give the herd a name."))
		if frappe.db.exists("Herds", name):
			frappe.throw(_("There is already a herd called {0}.").format(name))

		problems = _unmovable(animals)
		if problems:
			frappe.throw("\n".join(problems))

		herd = frappe.new_doc("Herds")
		herd.herd_name = name
		if d.get("description"):
			herd.description = d["description"]
		herd.insert()
		herd.submit()

		moved, from_herds = [], set()
		for animal in animals:
			was = frappe.db.get_value("Animal", animal, "current_herd")
			move = new_livestock_event(
				{"animal": animal, "operator": d.get("operator"),
				 "event_date": d.get("event_date") or today(),
				 "remarks": _("Moved into the new herd {0}").format(name)},
				"Movement",
			)
			move.new_herd = name
			move.current_herd = was or ""
			move.insert()
			move.submit()
			moved.append({"animal": animal, "from_herd": was})
			if was:
				from_herds.add(was)

		for old in from_herds:
			recompute_herd_count(old)
		recompute_herd_count(name)

		ration = None
		if d.get("lines"):
			ration = set_standing_ration(
				name, d["lines"],
				ration_item=(d.get("ration_item") or "").strip() or None,
			)

		return {
			"ok": True,
			"herd": name,
			"moved": moved,
			"heads": frappe.db.get_value("Herds", name, "number_of_animals"),
			"emptied_from": sorted(from_herds),
			"ration": ration,
		}

	return run(go, "livestock create_herd failed")


def _unmovable(animals):
	"""Everything wrong with the selection, said at once.

	All of it, not the first one: a person picking thirty cows off a list wants
	to hear about all four problems before they fix any of them, not to be sent
	round the loop four times.
	"""
	problems = []
	seen = set()
	for animal in animals:
		if animal in seen:
			problems.append(_("{0} is on the list twice.").format(animal))
			continue
		seen.add(animal)
		row = frappe.db.get_value("Animal", animal, ["disabled", "status"], as_dict=True)
		if not row:
			problems.append(_("{0} is not an animal on this farm.").format(animal))
		elif row.disabled:
			problems.append(
				_("{0} has left the farm ({1}) and cannot join a herd.").format(
					animal, (row.status or "gone").lower())
			)
	return problems
