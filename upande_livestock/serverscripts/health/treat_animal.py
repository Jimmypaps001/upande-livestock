# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Treat an animal: into her open file, or into a new one opened for it."""

import frappe
from frappe import _
from frappe.utils import today

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.health_case import (
	TREATING_STATUSES,
	open_case_for,
	open_file,
	treatment_row,
)


@frappe.whitelist()
def treat_animal(payload):
	"""Record a treatment, opening a file for it if she has none.

	THE ONE DOOR IN. Treating a cow and opening a file for her were two screens
	that knew nothing about each other: drugs went out of the store against a
	case somebody had remembered to open, or against no case at all, and a case
	could be opened for an animal nobody was treating. This endpoint is the only
	way a case is opened from a treatment, and the only way a treatment reaches
	a case.

	IT NEVER DECIDES TO OPEN ONE. `open_new` has to be said, because opening a
	second file for an illness already being treated is exactly the mistake that
	makes a farm's case history unreadable — three files for one bout of
	mastitis, none of them the whole story. The caller is told what she already
	has (see case_for_animal) and answers for it.

	And a treatment given months after the last one is not the same illness. The
	answer says which file it went into and whether that file is new, so the
	person at the crush can see they have started a fresh one rather than
	writing into a file from last season.
	"""

	def go():
		guard("Livestock Health Case")
		d = as_dict(payload)
		animal = (d.get("animal") or "").strip()
		if not animal:
			frappe.throw(_("Select an animal."))
		if not frappe.db.exists("Animal", animal):
			frappe.throw(_("{0} is not an animal on this farm.").format(animal))

		rows = [
			t for t in (d.get("treatments") or [])
			if t.get("drug_item") or t.get("drug_name_text")
		]
		if not rows:
			frappe.throw(_("Say what she was given. A treatment with no drug on it is a note."))

		standing = open_case_for(animal)
		named = (d.get("case") or "").strip()
		opened = False

		if named:
			case = frappe.get_doc("Livestock Health Case", named)
			if case.animal != animal:
				frappe.throw(_("Case {0} is not {1}'s.").format(named, animal))
			if case.case_status not in TREATING_STATUSES:
				frappe.throw(
					_("Case {0} is closed ({1}). Open a new file rather than writing into "
					  "a closed one.").format(named, case.case_status)
				)
		elif d.get("open_new"):
			case = open_file(
				{
					**d,
					"opened_date": d.get("treatment_date") or d.get("event_date"),
					# Whoever is giving the drug opens the file when nobody else
					# is named — the Stock Entry goes out in that name.
					"opened_by": d.get("opened_by") or d.get("operator")
					             or rows[0].get("administered_by"),
				},
				opened_from=_("a treatment"),
			)
			opened = True
		elif standing:
			# She has a file and nobody said to start another. Writing into the
			# one she has is the only reading that is not a guess.
			case = frappe.get_doc("Livestock Health Case", standing["name"])
		else:
			frappe.throw(
				_("{0} has no open file. Say what is wrong with her and a new one will be "
				  "opened for this treatment.").format(animal)
			)

		before = {t.name for t in case.treatments or []}
		for t in rows:
			case.append("treatments", treatment_row(t, d.get("treatment_date")))
		if case.case_status == "Open":
			# She is being treated now, and the file should say so rather than
			# sitting at "Open" until somebody remembers to change it.
			case.case_status = "Under Treatment"
		case.flags.ignore_permissions = True
		case.save()
		case.reload()

		added = [t for t in case.treatments or [] if t.name not in before]
		return {
			"ok": True,
			"case": case.name,
			"animal": case.animal,
			"opened": opened,
			"case_status": case.case_status,
			"added": len(added),
			"treatments": len(case.treatments or []),
			"on": d.get("treatment_date") or today(),
			"stock_entry": (added[0].stock_entry_ref if added else "") or "",
		}

	return run(go, "livestock treat_animal failed")
