# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Small pictures for lists.

A list row shows a 38 px circle; fetching the full photo for it (about 100 KB)
makes scrolling the herd a download. Every image attached to an Animal, a
Livestock Event, a Health Case or a Diagnosis gets a ~240 px JPEG next to it as
`<name>_thumb.jpg`, and `File.thumbnail_url` points at it. The name is derived
from the file's own, so a thumbnail can be found from a bare `Animal.image`
URL with no query, and making one twice changes nothing.
"""

import io
import os

import frappe

THUMB_SIDE = 240
THUMB_MAX_BYTES = 15 * 1024
SUFFIX = "_thumb.jpg"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
DOCTYPES = ("Animal", "Livestock Event", "Livestock Health Case", "Livestock Diagnosis")


def _is_image(url):
	return bool(url) and os.path.splitext(url.split("?")[0])[1].lower() in IMAGE_EXTENSIONS


def thumb_url_for(url):
	"""The URL a thumbnail of `url` would have, or None if it is not a stored image."""
	if not _is_image(url) or not url.startswith(("/files/", "/private/files/")):
		return None
	stem = os.path.splitext(url)[0]
	if stem.endswith(SUFFIX[:-4]):
		return None
	return stem + SUFFIX


def _path(url):
	rel = url.lstrip("/")
	return frappe.get_site_path(*(["public", rel] if url.startswith("/files/") else [rel]))


def existing_thumb(url):
	"""The thumbnail URL if one is on disk, else None. Cheap enough for a whole herd."""
	t = thumb_url_for(url)
	return t if t and os.path.exists(_path(t)) else None


def make_thumb(url):
	"""Write the thumbnail of the stored image at `url`; return its URL, or None.

	Idempotent: a thumbnail newer than its source is left alone.
	"""
	t = thumb_url_for(url)
	if not t:
		return None
	src, dst = _path(url), _path(t)
	if not os.path.exists(src):
		return None
	if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
		return t
	from PIL import Image, ImageOps

	try:
		with Image.open(src) as im:
			im = ImageOps.exif_transpose(im)
			if im.mode in ("RGBA", "LA", "P"):
				im = im.convert("RGBA")
				bg = Image.new("RGB", im.size, (255, 255, 255))
				bg.paste(im, mask=im.getchannel("A"))
				im = bg
			else:
				im = im.convert("RGB")
			im.thumbnail((THUMB_SIDE, THUMB_SIDE))
			data = b""
			for q in (70, 60, 50, 40):
				buf = io.BytesIO()
				im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
				data = buf.getvalue()
				if len(data) <= THUMB_MAX_BYTES:
					break
	except Exception:
		frappe.log_error(f"thumbnail failed for {url}", "livestock thumbnail")
		return None
	with open(dst, "wb") as fh:
		fh.write(data)
	return t


def thumb_file(doc, method=None):
	"""File after_insert: thumbnail a picture attached to one of our doctypes."""
	if doc.attached_to_doctype not in DOCTYPES or doc.is_folder:
		return
	t = make_thumb(doc.file_url)
	if t and doc.thumbnail_url != t:
		doc.db_set("thumbnail_url", t, update_modified=False)


def thumb_animal(doc, method=None):
	"""Animal on_update: a changed profile picture gets its thumbnail."""
	if doc.image and (doc.is_new() or doc.has_value_changed("image")):
		make_thumb(doc.image)


def backfill():
	"""Thumbnail every existing picture. Safe to run again."""
	urls = set()
	for f in frappe.get_all(
		"File", filters={"attached_to_doctype": ["in", DOCTYPES], "is_folder": 0},
		fields=["name", "file_url"], limit_page_length=0,
	):
		if f.file_url and make_thumb(f.file_url):
			frappe.db.set_value("File", f.name, "thumbnail_url", thumb_url_for(f.file_url),
			                    update_modified=False)
	urls.update(frappe.get_all("Animal", filters={"image": ["is", "set"]}, pluck="image",
	                           limit_page_length=0))
	urls.update(frappe.get_all("Livestock Event", filters={"calf_photo": ["is", "set"]},
	                           pluck="calf_photo", limit_page_length=0))
	made = sum(1 for u in urls if make_thumb(u))
	frappe.db.commit()
	return made
