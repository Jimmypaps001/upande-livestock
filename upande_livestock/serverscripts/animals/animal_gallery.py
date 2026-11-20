# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""animal_gallery: split out of animals.animal_photos; that module still re-exports it, so the old dotted path resolves."""

import frappe
from frappe.utils import get_fullname

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.common import thumbs


@frappe.whitelist()
def animal_gallery(animal=None, payload=None):
	"""Every image linked to the animal, newest first.

	[{name, url, thumb, date, source, ref_doctype, ref_name, caption, uploaded_by}]
	with source one of Profile, Birth, Health case, Event. Three small reads
	find what hangs off her (events, cases, check-ups) and ONE grouped read of
	File fetches every attachment on all of it.
	"""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.animals.animal_photos import BIRTH_TYPES, LIMIT, _check_animal, _is_image


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
