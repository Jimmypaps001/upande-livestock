# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""An animal's photographs: the portfolio the page opens onto.

A picture is a File attached to the thing it is a picture OF: the Animal (her
portrait), her birth or calving event, one of her health cases, or any other
event or check-up. Nothing new is stored for the gallery; `animal_gallery` is a
read across those attachments, newest first, and `add_animal_photo` is the one
door a picture goes in by, so the rules (an animal's own open case, an
employee) live on the server and not in the phone.

THE PHONE RECORDS, THE SERVER DECIDES. The phone uploads the picture with the
ordinary `upload_file` (public, exactly as the calf photo is, so a plain image
request loads it with no session cookie) and then names it here with the
purpose. Here it is checked, attached and, for a profile photo, set as
`Animal.image`. A photo that is refused stays an unattached upload and is never
shown anywhere.
"""

import os

import frappe
from frappe import _
from frappe.utils import get_fullname

from upande_livestock.serverscripts.common import thumbs
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.common.guards import require_employee
from upande_livestock.serverscripts.common.envelope import LIVESTOCK_ROLES
from upande_livestock.serverscripts.common.health_case import TREATING_STATUSES

CONTEXTS = ("health_case", "birth", "profile")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp")
BIRTH_TYPES = ("Birth", "Calving")
LIMIT = 300


def _is_image(url):
	return bool(url) and os.path.splitext(url.split("?")[0])[1].lower() in IMAGE_EXTENSIONS


def _check_animal(animal, ptype="read"):
	if not animal or not frappe.db.exists("Animal", animal):
		frappe.throw(_("Select an animal."))
	if not frappe.has_permission("Animal", ptype, animal):
		frappe.throw(_("You are not permitted to {0} {1}.").format(_(ptype), animal), frappe.PermissionError)


@frappe.whitelist()
def animal_gallery(animal=None, payload=None):
	"""Every image linked to the animal, newest first.

	[{name, url, thumb, date, source, ref_doctype, ref_name, caption, uploaded_by}]
	with source one of Profile, Birth, Health case, Event. Three small reads
	find what hangs off her (events, cases, check-ups) and ONE grouped read of
	File fetches every attachment on all of it.
	"""

	def go():
		guard_read("Animal")
		a = animal or as_dict(payload).get("animal")
		a = (a or "").strip()
		_check_animal(a)

		events = frappe.get_all(
			"Livestock Event",
			or_filters=[["animal", "=", a], ["dam", "=", a]],
			filters={"docstatus": ["<", 2]},
			fields=["name", "event_type", "event_date", "animal", "dam", "calf_photo", "owner"],
			limit=1000,
		)
		# A dam's gallery shows the calving, not every event her calf had.
		events = [e for e in events if e.animal == a or (e.dam == a and e.event_type in BIRTH_TYPES)]
		cases = frappe.get_all(
			"Livestock Health Case", filters={"animal": a, "docstatus": ["<", 2]}, pluck="name"
		)
		checks = frappe.get_all(
			"Livestock Diagnosis", filters={"animal": a, "docstatus": ["<", 2]}, pluck="name"
		)

		targets = {"Animal": [a]}
		if events:
			targets["Livestock Event"] = [e.name for e in events]
		if cases:
			targets["Livestock Health Case"] = cases
		if checks:
			targets["Livestock Diagnosis"] = checks

		F = frappe.qb.DocType("File")
		cond = None
		for dt, names in targets.items():
			c = (F.attached_to_doctype == dt) & F.attached_to_name.isin(names)
			cond = c if cond is None else (cond | c)
		files = (
			frappe.qb.from_(F)
			.select(F.name, F.file_url, F.thumbnail_url, F.creation, F.owner,
			        F.attached_to_doctype, F.attached_to_name, F.livestock_caption)
			.where(cond & (F.is_folder == 0))
			.orderby(F.creation, order=frappe.qb.desc)
			.limit(LIMIT)
			.run(as_dict=True)
		)

		by_event = {e.name: e for e in events}
		out, seen = [], set()

		def source_of(f):
			dt, nm = f.attached_to_doctype, f.attached_to_name
			if dt == "Animal":
				return "Profile"
			if dt == "Livestock Health Case":
				return "Health case"
			if dt == "Livestock Event" and by_event[nm].event_type in BIRTH_TYPES:
				return "Birth"
			return "Event"

		for f in files:
			if not _is_image(f.file_url) or f.file_url in seen:
				continue
			seen.add(f.file_url)
			out.append({
				"name": f.name, "url": f.file_url, "thumb": f.thumbnail_url or thumbs.existing_thumb(f.file_url),
				"date": str(f.creation), "source": source_of(f),
				"ref_doctype": f.attached_to_doctype, "ref_name": f.attached_to_name,
				"caption": f.livestock_caption or "", "uploaded_by": f.owner,
			})

		# Pictures held only as a field value (a calf's photo from the calving
		# form, an image set on the Animal) have no File attached to the thing.
		extra = []
		image = frappe.db.get_value("Animal", a, ["image", "modified", "owner"], as_dict=True)
		if image and image.image:
			extra.append((image.image, image.modified, image.owner, "Profile", "Animal", a))
		for e in events:
			if e.calf_photo:
				extra.append((e.calf_photo, e.event_date, e.owner, "Birth", "Livestock Event", e.name))
		for url, date, owner, source, dt, nm in extra:
			if _is_image(url) and url not in seen:
				seen.add(url)
				out.append({"name": None, "url": url, "thumb": thumbs.existing_thumb(url), "date": str(date),
				            "source": source, "ref_doctype": dt, "ref_name": nm,
				            "caption": "", "uploaded_by": owner})

		out.sort(key=lambda r: r["date"], reverse=True)
		names = {r["uploaded_by"] for r in out if r["uploaded_by"]}
		who = {n: get_fullname(n) for n in names}
		for r in out:
			r["uploaded_by"] = who.get(r["uploaded_by"], r["uploaded_by"] or "")
		return {"ok": True, "animal": a, "photos": out}

	return run(go, "livestock animal_gallery failed")


def _birth_event(animal):
	"""The event a birth photo belongs to: her own Birth (a calf), else her latest calving."""
	own = frappe.get_all(
		"Livestock Event",
		filters={"animal": animal, "event_type": "Birth", "docstatus": ["<", 2]},
		pluck="name", order_by="event_date desc, creation desc", limit=1,
	)
	if own:
		return own[0]
	rows = []
	for flt in ({"animal": animal, "event_type": "Calving"}, {"dam": animal, "event_type": "Birth"}):
		rows += frappe.get_all(
			"Livestock Event", filters={**flt, "docstatus": ["<", 2]},
			fields=["name", "event_date", "creation"], order_by="event_date desc, creation desc", limit=1,
		)
	rows.sort(key=lambda r: (str(r.event_date), str(r.creation)), reverse=True)
	return rows[0].name if rows else None


def _attach(file_url, doctype, name, caption=None):
	"""Attach the uploaded file to `doctype/name` and return the File."""
	if not file_url or not file_url.startswith(("/files/", "/private/files/")):
		frappe.throw(_("That is not an uploaded file."))
	if not _is_image(file_url):
		frappe.throw(_("Only pictures can be added."))
	mine = frappe.db.get_value(
		"File", {"file_url": file_url, "attached_to_doctype": doctype, "attached_to_name": name}
	)
	if mine:
		doc = frappe.get_doc("File", mine)
	else:
		loose = frappe.get_all(
			"File", filters={"file_url": file_url, "attached_to_name": ["is", "not set"]},
			pluck="name", limit=1,
		)
		if loose:
			doc = frappe.get_doc("File", loose[0])
			doc.attached_to_doctype, doc.attached_to_name = doctype, name
		else:
			if not frappe.db.exists("File", {"file_url": file_url}):
				frappe.throw(_("That file was not found; upload it again."))
			doc = frappe.get_doc({
				"doctype": "File", "file_url": file_url, "file_name": os.path.basename(file_url),
				"attached_to_doctype": doctype, "attached_to_name": name,
				"is_private": 1 if file_url.startswith("/private/") else 0,
			})
	if caption:
		doc.livestock_caption = caption.strip()[:140]
	doc.flags.ignore_permissions = True
	doc.save() if doc.get("name") else doc.insert()
	return doc


def _keep_old_profile(animal):
	"""A profile photo being replaced stays in her gallery as an attached File."""
	old = frappe.db.get_value("Animal", animal, "image")
	if not old or not _is_image(old):
		return
	if frappe.db.exists("File", {"file_url": old, "attached_to_doctype": "Animal", "attached_to_name": animal}):
		return
	if frappe.db.exists("File", {"file_url": old}):
		_attach(old, "Animal", animal)


@frappe.whitelist()
def add_animal_photo(animal=None, file_url=None, context=None, ref=None, caption=None, payload=None):
	"""Attach an uploaded picture to the animal for a stated purpose.

	context health_case: `ref` is one of HER cases and it must be open (Open or
	Under Treatment). birth: her Birth event (a calf), or her latest calving
	(a dam). profile: becomes Animal.image; the old picture stays in the gallery.
	"""

	def go():
		d = as_dict(payload) if payload else {}
		a = (animal or d.get("animal") or "").strip()
		url = (file_url or d.get("file_url") or "").strip()
		ctx = context or d.get("context")
		rf = ref or d.get("ref")
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
