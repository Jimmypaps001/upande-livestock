# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.tests.test_operations import _suspend_sex_routing

from upande_livestock.serverscripts.common.animal import create_calf

from upande_livestock.serverscripts.common.animal import recompute_herd_count

from upande_livestock.serverscripts.common.animal import resolve_calf_herd


def make_herd(name, **kwargs):
	if frappe.db.exists("Herds", name):
		return frappe.get_doc("Herds", name)
	return frappe.get_doc({"doctype": "Herds", "herd_name": name, **kwargs}).insert()


def make_dam(tag="TEST-DAM-1", herd=None):
	if frappe.db.exists("Animal", tag):
		return frappe.get_doc("Animal", tag)
	return frappe.get_doc(
		{
			"doctype": "Animal",
			"tag_number": tag,
			"burn_name": tag,
			"sex": "Female",
			"status": "Active",
			"breed": frappe.db.get_value("Breed", {}, "name"),
			"current_herd": herd,
		}
	).insert()


class TestResolveCalfHerd(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_single_value("Livestock Settings", "default_calf_herd", None)
		frappe.clear_cache()

	def tearDown(self):
		frappe.db.set_single_value("Livestock Settings", "default_calf_herd", None)
		frappe.clear_cache()

	def test_explicit_setting_wins(self):
		herd = make_herd("TEST-CALF-EXPLICIT", min_age=0, max_age=1)
		self.addCleanup(_delete_and_commit, "Herds", herd.name)
		frappe.db.set_single_value("Livestock Settings", "default_calf_herd", herd.name)
		frappe.clear_cache()
		self.assertEqual(resolve_calf_herd(), herd.name)

	def test_falls_back_to_the_calf_rearing_flag(self):
		herd = make_herd("TEST-CALF-REARING", min_age=0, max_age=1, custom_is_calf_rearing=1)
		self.addCleanup(_delete_and_commit, "Herds", herd.name)
		self.assertEqual(resolve_calf_herd(), herd.name)


class TestCreateCalf(IntegrationTestCase):
	def setUp(self):
		_suspend_sex_routing(self)
		self.herd = make_herd("TEST-CALF-HERD", min_age=0, max_age=1, custom_is_calf_rearing=1)
		self.addCleanup(_delete_and_commit, "Herds", self.herd.name)
		self.dam = make_dam("TEST-DAM-1", herd=self.herd.name)
		self.addCleanup(_delete_and_commit, "Animal", self.dam.name)
		for tag in ("TEST-CALF-A", "TEST-CALF-B"):
			if frappe.db.exists("Animal", tag):
				frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
				frappe.db.commit()
			self.addCleanup(_delete_if_exists, "Animal", tag)

	def test_creates_the_animal_in_the_resolved_calf_herd(self):
		name = create_calf(self.dam.name, "TEST-CALF-A", "Female", "2026-05-01")
		calf = frappe.get_doc("Animal", name)
		self.assertEqual(calf.current_herd, self.herd.name)
		self.assertEqual(calf.sex, "Female")
		self.assertEqual(calf.dam, self.dam.name)
		self.assertEqual(calf.origin, "Born on Farm")
		self.assertEqual(calf.status, "Active")
		self.assertEqual(calf.repro_status, "Calf")
		self.assertEqual(str(calf.date_of_birth), "2026-05-01")
		self.assertEqual(str(calf.acquisition_date), "2026-05-01")

	def test_inherits_the_dam_breed(self):
		name = create_calf(self.dam.name, "TEST-CALF-B", "Male", "2026-05-02")
		self.assertEqual(frappe.db.get_value("Animal", name, "breed"), self.dam.breed)

	def test_duplicate_tag_throws(self):
		create_calf(self.dam.name, "TEST-CALF-A", "Female", "2026-05-01")
		with self.assertRaises(frappe.exceptions.ValidationError):
			create_calf(self.dam.name, "TEST-CALF-A", "Female", "2026-05-03")

	def test_explicit_herd_overrides_resolution(self):
		other = make_herd("TEST-OTHER-HERD", min_age=2, max_age=5)
		self.addCleanup(_delete_and_commit, "Herds", other.name)
		name = create_calf(self.dam.name, "TEST-CALF-B", "Female", "2026-05-04", herd=other.name)
		self.assertEqual(frappe.db.get_value("Animal", name, "current_herd"), other.name)

	def test_recompute_herd_count_matches_reality(self):
		create_calf(self.dam.name, "TEST-CALF-A", "Female", "2026-05-01")
		recompute_herd_count(self.herd.name)
		expected = frappe.db.count("Animal", {"current_herd": self.herd.name, "docstatus": ["!=", 2]})
		self.assertEqual(frappe.db.get_value("Herds", self.herd.name, "number_of_animals"), expected)


def _delete_and_commit(doctype, name):
	if frappe.db.exists(doctype, name):
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		frappe.db.commit()


def _delete_if_exists(doctype, name):
	if frappe.db.exists(doctype, name):
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		frappe.db.commit()
