# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Change an animal's number — the sequence and the year, nothing else."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import animal_id
from upande_livestock.serverscripts.common.envelope import as_dict, run


@frappe.whitelist()
def rename_animal(payload):
	"""Renumber an animal.

	Write permission on Animal, not create: today that is System Manager and
	Livestock Manager only, which is the point. An attendant booking a birth
	reads the number the system allocated; they do not get to renumber the herd.

	The letter is never an input. It comes from the animal's sex, so a rename
	cannot quietly move a bull into the heifer series.
	"""

	def go():
		if not frappe.has_permission("Animal", "write"):
			frappe.throw(_("You are not permitted to renumber animals."), frappe.PermissionError)

		d = as_dict(payload)
		name = (d.get("animal") or "").strip()
		if not name:
			frappe.throw(_("Select the animal to renumber."))
		if not frappe.db.exists("Animal", name):
			frappe.throw(_("{0} is not an animal on this farm.").format(name))

		new_id = animal_id.tidy(d.get("new_id") or "")
		sex = frappe.db.get_value("Animal", name, "sex")
		got = animal_id.assert_assignable(new_id, sex, current=name)

		if got["id"] == name:
			return {"ok": True, "name": name, "renamed_from": name, "unchanged": True}

		# merge=False: a number that belongs to another animal was already
		# refused above, and merging would fold two animals' histories together.
		# frappe.rename_doc enforces permissions itself; the write check above is
		# the livestock-specific gate on top of it.
		frappe.rename_doc("Animal", name, got["id"], merge=False, force=False)
		# tag_number is the autoname source, so it has to follow the name or the
		# next save would rename the record straight back.
		frappe.db.set_value("Animal", got["id"], "tag_number", got["id"], update_modified=False)

		return {"ok": True, "name": got["id"], "renamed_from": name, "unchanged": False}

	return run(go, "livestock rename_animal failed")
