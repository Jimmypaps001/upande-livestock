# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The animal's portfolio: what goes in (add_animal_photo) and what comes out
(animal_gallery). Cases and events go in straight and submitted; how they are
recorded is tested elsewhere."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.animals.animal_photos import add_animal_photo, animal_gallery
from upande_livestock.serverscripts.tests.test_employee_gate import _drop_all, _user
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge, _purge_events_for

COW, OTHER, CALF = "ZZ PHOTO COW", "ZZ PHOTO OTHER", "ZZ PHOTO CALF"
NAMES = [f"zz-photo-{i}.png" for i in range(8)]
URLS = []  # the URLs Frappe gave them, set up per test


def _png(seed):
	"""A real, distinct picture (File strips EXIF, so the bytes must decode)."""
	import io
	from PIL import Image
	buf = io.BytesIO()
	Image.new("RGB", (4, 4), (hash(seed) % 255, len(seed) * 7 % 255, 90)).save(buf, "PNG")
	return buf.getvalue()


def _file(name):
	"""An uploaded, unattached File, as `upload_file` leaves it. Frappe picks
	the final name (it suffixes one that is taken), so the URL is returned."""
	f = frappe.get_doc({"doctype": "File", "file_name": name, "is_private": 0, "content": _png(name)})
	f.insert(ignore_permissions=True)
	return f.file_url


def _case(animal, status="Open"):
	c = frappe.get_doc({"doctype": "Livestock Health Case", "animal": animal, "case_status": status,
	                    "opened_date": today()})
	c.flags.ignore_validate = True
	c.db_insert()
	frappe.db.set_value("Livestock Health Case", c.name, "docstatus", 1)
	return c.name


def _event(animal, kind, ago=0, **kw):
	ev = frappe.get_doc({"doctype": "Livestock Event", "event_type": kind, "animal": animal,
	                     "event_date": add_days(today(), -ago), **kw})
	ev.flags.ignore_validate = True
	ev.db_insert()
	frappe.db.set_value("Livestock Event", ev.name, "docstatus", 1)
	return ev.name


class TestAnimalPhotos(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._tidy()
		_make_cow(COW)
		_make_cow(OTHER)
		URLS[:] = [_file(n) for n in NAMES]
		self.addCleanup(self._tidy)

	def _tidy(self):
		frappe.set_user("Administrator")
		for dt in ("Livestock Health Case",):
			for n in frappe.get_all(dt, filters={"animal": ["in", [COW, OTHER]]}, pluck="name"):
				frappe.db.delete("File", {"attached_to_doctype": dt, "attached_to_name": n})
				frappe.db.delete(dt, {"name": n})
		for tag in (COW, OTHER, CALF):
			for n in frappe.get_all("Livestock Event", or_filters=[["animal", "=", tag], ["dam", "=", tag]], pluck="name"):
				frappe.db.delete("File", {"attached_to_doctype": "Livestock Event", "attached_to_name": n})
			_purge_events_for(tag)
			frappe.db.delete("File", {"attached_to_doctype": "Animal", "attached_to_name": tag})
			_purge("Animal", tag)
		for n in frappe.get_all("File", filters={"file_name": ["like", "zz-photo-%"]}, pluck="name"):
			frappe.delete_doc("File", n, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _add(self, url, ctx, ref=None, animal=COW, **kw):
		frappe.db.commit()  # a refusal rolls back, as it does for a request
		return add_animal_photo(animal=animal, file_url=url, context=ctx, ref=ref, **kw)

	def test_a_photo_goes_on_an_open_case(self):
		case = _case(COW)
		res = self._add(URLS[0], "health_case", case, caption="swollen quarter")
		self.assertTrue(res.get("ok"), res)
		self.assertEqual(frappe.db.get_value("File", res["file"], "attached_to_name"), case)
		got = animal_gallery(animal=COW)["photos"]
		self.assertEqual([(p["url"], p["source"], p["caption"]) for p in got],
		                 [(URLS[0], "Health case", "swollen quarter")])

	def test_a_case_under_treatment_is_open_too(self):
		self.assertTrue(self._add(URLS[0], "health_case", _case(COW, "Under Treatment")).get("ok"))

	def test_a_closed_case_is_refused(self):
		res = self._add(URLS[0], "health_case", _case(COW, "Recovered"))
		self.assertIn("error", res)
		self.assertIn("open", res["error"])
		self.assertEqual(animal_gallery(animal=COW)["photos"], [])
		self.assertFalse(frappe.db.exists("File", {"file_url": URLS[0], "attached_to_doctype": "Livestock Health Case"}))

	def test_another_animals_case_is_refused(self):
		res = self._add(URLS[0], "health_case", _case(OTHER))
		self.assertIn("is not a health case of", res["error"])

	def test_a_health_photo_needs_a_case_and_a_known_context(self):
		self.assertIn("Choose the health case", self._add(URLS[0], "health_case")["error"])
		self.assertIn("error", self._add(URLS[0], "holiday"))
		self.assertIn("error", self._add("/etc/passwd", "profile"))

	def test_a_birth_photo_goes_on_the_calvings_event(self):
		_make_cow(CALF, months_old=1)
		birth = _event(CALF, "Birth", 20, dam=COW)
		res = self._add(URLS[1], "birth", animal=CALF)
		self.assertEqual(res["ref_name"], birth)
		# The dam sees it too, as her latest calving.
		self.assertEqual([p["source"] for p in animal_gallery(animal=COW)["photos"]], ["Birth"])
		self.assertEqual(self._add(URLS[2], "birth")["ref_name"], birth)

	def test_a_birth_photo_with_no_birth_is_refused(self):
		self.assertIn("no birth or calving", self._add(URLS[1], "birth")["error"])

	def test_a_profile_photo_sets_the_image_and_keeps_the_old_one(self):
		frappe.db.set_value("Animal", COW, "image", URLS[3])
		res = self._add(URLS[4], "profile")
		self.assertTrue(res.get("ok"), res)
		self.assertEqual(frappe.db.get_value("Animal", COW, "image"), URLS[4])
		urls = {p["url"] for p in animal_gallery(animal=COW)["photos"]}
		self.assertEqual(urls, {URLS[3], URLS[4]})
		self.assertTrue(frappe.db.exists("File", {"file_url": URLS[3], "attached_to_name": COW}))

	def test_the_gallery_is_newest_first_and_names_its_sources(self):
		case = _case(COW)
		_event(COW, "Check Up", 3)
		ev = _event(COW, "Check Up", 2)
		self._add(URLS[5], "health_case", case)
		self._add(URLS[6], "profile")
		fd = frappe.db.get_value("File", {"file_url": URLS[7]}, "name")
		frappe.db.set_value("File", fd, {"attached_to_doctype": "Livestock Event", "attached_to_name": ev})
		frappe.db.set_value("File", fd, "creation", add_days(today(), -30), update_modified=False)
		got = animal_gallery(animal=COW)["photos"]
		self.assertEqual([p["url"] for p in got], [URLS[6], URLS[5], URLS[7]])
		self.assertEqual([p["source"] for p in got], ["Profile", "Health case", "Event"])
		self.assertTrue(all(p["uploaded_by"] for p in got))

	def test_a_view_only_user_cannot_add(self):
		hand = _user("Livestock Manager", with_employee=False)
		frappe.db.commit()
		self.addCleanup(_drop_all)
		frappe.set_user(hand)
		res = self._add(URLS[0], "profile")
		self.assertEqual(res.get("code"), "not_employee")
		# ... but may look.
		self.assertTrue(animal_gallery(animal=COW).get("ok"))
