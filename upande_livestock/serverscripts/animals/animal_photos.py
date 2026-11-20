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

from upande_livestock.serverscripts.common.idempotency import idempotent
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


def _case_of(client_ref):
	"""The health case a filed treatment (by its client_ref) opened or added to."""
	import json

	raw = frappe.db.get_value("Livestock Client Ref", str(client_ref).strip()[:140], "result")
	try:
		return (json.loads(raw or "{}") or {}).get("case")
	except Exception:
		return None


# The endpoints split out into their own modules. Imported here so the dotted paths the phone and
# the desk already call still resolve (Frappe checks the whitelist by function identity).
# Last, because each of them imports helpers from this module.
from upande_livestock.serverscripts.animals.add_animal_photo import add_animal_photo  # noqa: E402,F401
from upande_livestock.serverscripts.animals.animal_gallery import animal_gallery  # noqa: E402,F401
