# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""add_animal_photo: split out of animals.animal_photos; that module still re-exports it, so the old dotted path resolves."""

from frappe import _
import frappe

from upande_livestock.serverscripts.common.envelope import LIVESTOCK_ROLES
from upande_livestock.serverscripts.common.health_case import TREATING_STATUSES
from upande_livestock.serverscripts.common.envelope import as_dict, run
from upande_livestock.serverscripts.common.idempotency import idempotent
from upande_livestock.serverscripts.common.guards import require_employee


@frappe.whitelist()
@idempotent
def add_animal_photo(animal=None, file_url=None, context=None, ref=None, caption=None, payload=None, ref_client_ref=None):
	"""Attach an uploaded picture to the animal for a stated purpose.

	context health_case: `ref` is one of HER cases and it must be open (Open or
	Under Treatment). birth: her Birth event (a calf), or her latest calving
	(a dam). profile: becomes Animal.image; the old picture stays in the gallery.
	"""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.animals.animal_photos import CONTEXTS, _attach, _birth_event, _case_of, _check_animal, _keep_old_profile


	def go():
		d = as_dict(payload) if payload else {}
		a = (animal or d.get("animal") or "").strip()
		url = (file_url or d.get("file_url") or "").strip()
		ctx = context or d.get("context")
		rf = ref or d.get("ref")
		# A photo taken with a treatment that was still in the phone's queue does not
		# know its health case yet; it names the treatment's client_ref and the case is
		# read from the answer the server kept for it.
		linked = ref_client_ref or d.get("ref_client_ref")
		if not rf and linked:
			rf = _case_of(linked)
		cap = caption or d.get("caption")

		require_employee("Animal")
		if ctx not in CONTEXTS:
			frappe.throw(_("Say what the photo is for: a health case, a birth or her profile."))
		_check_animal(a)
		if not url:
			frappe.throw(_("Add a picture."))

		if ctx == "health_case":
			if not rf:
				frappe.throw(_("Choose the health case this photo belongs to."))
			case = frappe.db.get_value(
				"Livestock Health Case", rf, ["animal", "case_status", "docstatus"], as_dict=True
			)
			if not case or case.animal != a:
				frappe.throw(_("{0} is not a health case of {1}.").format(rf, a))
			if case.docstatus != 1 or case.case_status not in TREATING_STATUSES:
				frappe.throw(_("Health case {0} is {1}; photos can only be added while it is open.").format(
					rf, case.case_status))
			target = ("Livestock Health Case", rf)
		elif ctx == "birth":
			ev = _birth_event(a)
			if not ev:
				frappe.throw(_("{0} has no birth or calving on record to attach a photo to.").format(a))
			target = ("Livestock Event", ev)
		else:
			if not (frappe.has_permission("Animal", "write", a)
			        or set(frappe.get_roles()) & set(LIVESTOCK_ROLES)):
				frappe.throw(_("You are not permitted to change {0}.").format(a), frappe.PermissionError)
			_keep_old_profile(a)
			target = ("Animal", a)

		f = _attach(url, target[0], target[1], cap)
		if ctx == "profile":
			frappe.db.set_value("Animal", a, "image", f.file_url)
		return {"ok": True, "animal": a, "context": ctx, "file": f.name, "url": f.file_url,
		        "ref_doctype": target[0], "ref_name": target[1]}

	return run(go, "livestock add_animal_photo failed")
