# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The phone's offline animal store is kept current by `animals_since`.

Three things matter: the first call returns every active animal and nothing
retired; a later call returns only what changed; and an animal that stops being
active, or is deleted, is named in `removed` so the phone can drop it.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now

from upande_livestock.serverscripts.mobile.animals_since import animals_since
from upande_livestock.serverscripts.tests.test_animal import make_dam


def _names(result):
	return {a["name"] for a in result["animals"]}


class TestAnimalsSince(IntegrationTestCase):
	def setUp(self):
		self.a = make_dam("TEST-SINCE-A")
		self.b = make_dam("TEST-SINCE-B")
		self.past = add_to_date(now(), seconds=-60)
		# Older than `past`, so a delta from `past` must leave it out.
		frappe.db.set_value("Animal", self.b.name, "modified", add_to_date(now(), hours=-5),
		                    update_modified=False)

	def tearDown(self):
		for n in ("TEST-SINCE-A", "TEST-SINCE-B"):
			if frappe.db.exists("Animal", n):
				frappe.delete_doc("Animal", n, force=True, ignore_permissions=True)

	def test_full_set_has_active_animals_with_the_detail_fields(self):
		r = animals_since()
		self.assertTrue(r["ok"])
		self.assertTrue(r["full"])
		self.assertEqual(r["removed"], [])
		self.assertTrue({self.a.name, self.b.name} <= _names(r))
		row = next(x for x in r["animals"] if x["name"] == self.a.name)
		for key in ("tag", "animal_name", "sex", "breed", "dob", "herd", "status",
		            "image", "dam", "sire", "modified"):
			self.assertIn(key, row)
		self.assertTrue(r["server_time"])

	def test_full_set_leaves_out_retired_animals(self):
		frappe.db.set_value("Animal", self.a.name, "status", "Sold")
		self.assertNotIn(self.a.name, _names(animals_since()))

	def test_delta_returns_only_what_changed(self):
		frappe.db.set_value("Animal", self.a.name, "breed", self.a.breed)  # touches modified
		r = animals_since(self.past)
		self.assertFalse(r["full"])
		self.assertIn(self.a.name, _names(r))
		self.assertNotIn(self.b.name, _names(r))

	def test_delta_names_animals_that_stopped_being_active(self):
		frappe.db.set_value("Animal", self.a.name, "status", "Culled")
		frappe.db.set_value("Animal", self.b.name, "disabled", 1)
		r = animals_since(self.past)
		self.assertIn(self.a.name, r["removed"])
		self.assertNotIn(self.a.name, _names(r))
		# b was last modified before `past` by timestamp, but set_value stamped it now.
		self.assertIn(self.b.name, r["removed"])

	def test_delta_names_deleted_animals(self):
		frappe.delete_doc("Animal", self.a.name, force=True, ignore_permissions=True)
		r = animals_since(self.past)
		self.assertIn(self.a.name, r["removed"])

	def test_a_user_who_cannot_read_animals_is_refused(self):
		frappe.set_user("Guest")
		try:
			r = animals_since()
		finally:
			frappe.set_user("Administrator")
		self.assertIn("error", r)
