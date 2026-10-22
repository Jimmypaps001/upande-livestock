# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Thumbnails for lists: made on attach, found by URL, carried to the phone."""

import io
import os

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.animals.animal_photos import animal_gallery
from upande_livestock.serverscripts.common import thumbs
from upande_livestock.serverscripts.mobile.animals_since import animals_since
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge

COW = "ZZ THUMB COW"


def _jpeg(w=1600, h=1200):
	import random
	from PIL import Image
	rnd = random.Random(7)
	im = Image.frombytes("RGB", (w, h), bytes(rnd.randrange(256) for _ in range(w * h * 3)))
	buf = io.BytesIO()
	im.save(buf, "JPEG", quality=90)
	return buf.getvalue()


def _size(url):
	from PIL import Image
	with Image.open(thumbs._path(url)) as im:
		return im.size


class TestThumbs(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._tidy()
		_make_cow(COW)
		self.addCleanup(self._tidy)

	def _tidy(self):
		frappe.set_user("Administrator")
		frappe.db.delete("File", {"attached_to_doctype": "Animal", "attached_to_name": COW})
		for n in frappe.get_all("File", filters={"file_name": ["like", "zz-thumb-%"]}, pluck="name"):
			frappe.delete_doc("File", n, force=True, ignore_permissions=True)
		_purge("Animal", COW)
		frappe.db.commit()

	def _attach(self, name="zz-thumb-a.jpg", content=None):
		f = frappe.get_doc({
			"doctype": "File", "file_name": name, "is_private": 0, "content": content or _jpeg(),
			"attached_to_doctype": "Animal", "attached_to_name": COW,
		})
		f.insert(ignore_permissions=True)
		return f

	def test_an_attached_picture_gets_a_small_jpeg(self):
		f = self._attach()
		t = frappe.db.get_value("File", f.name, "thumbnail_url")
		self.assertEqual(t, thumbs.thumb_url_for(f.file_url))
		self.assertTrue(t.endswith("_thumb.jpg"))
		self.assertLessEqual(os.path.getsize(thumbs._path(t)), thumbs.THUMB_MAX_BYTES)
		self.assertLessEqual(max(_size(t)), thumbs.THUMB_SIDE)

	def test_making_one_twice_changes_nothing(self):
		f = self._attach()
		path = thumbs._path(thumbs.thumb_url_for(f.file_url))
		before = os.path.getmtime(path)
		thumbs.make_thumb(f.file_url)
		self.assertEqual(os.path.getmtime(path), before)

	def test_a_picture_attached_to_something_else_is_left_alone(self):
		f = frappe.get_doc({"doctype": "File", "file_name": "zz-thumb-b.jpg", "is_private": 0,
		                    "content": _jpeg(400, 300)})
		f.insert(ignore_permissions=True)
		self.assertIsNone(thumbs.existing_thumb(f.file_url))

	def test_a_thumbnail_is_not_thumbnailed_and_other_urls_are_refused(self):
		self.assertIsNone(thumbs.thumb_url_for("/files/a_thumb.jpg"))
		self.assertIsNone(thumbs.thumb_url_for("https://elsewhere/x.jpg"))
		self.assertIsNone(thumbs.thumb_url_for("/files/x.pdf"))
		self.assertIsNone(thumbs.make_thumb("/files/zz-thumb-missing.jpg"))

	def test_the_animal_row_and_the_gallery_carry_the_thumb(self):
		f = self._attach()
		frappe.db.set_value("Animal", COW, "image", f.file_url)
		frappe.db.commit()
		row = next(a for a in animals_since()["animals"] if a["name"] == COW)
		self.assertEqual(row["thumb"], thumbs.thumb_url_for(f.file_url))
		photos = animal_gallery(animal=COW)["photos"]
		self.assertEqual(photos[0]["thumb"], thumbs.thumb_url_for(f.file_url))

	def test_a_row_with_no_picture_has_no_thumb(self):
		row = next(a for a in animals_since()["animals"] if a["name"] == COW)
		self.assertIsNone(row["thumb"])

	def test_backfill_makes_the_missing_ones(self):
		f = self._attach()
		os.remove(thumbs._path(thumbs.thumb_url_for(f.file_url)))
		thumbs.backfill()
		self.assertTrue(thumbs.existing_thumb(f.file_url))
