# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Herds, animals and weight records built inside a test, so the beef tests run
on an empty site instead of skipping. Everything is created in the test's own
transaction; IntegrationTestCase rolls it back."""

import frappe
from frappe.utils import add_days, today


def clear_bands():
	"""Take every existing Fattening herd off the ladder for this test."""
	for name in frappe.get_all("Herds", filters={"herd_class": "Fattening"}, pluck="name"):
		frappe.db.set_value("Herds", name, "herd_class", "Other")


def make_herd(name, herd_class="Other", min_kg=0, max_kg=0, **extra):
	doc = frappe.get_doc({
		"doctype": "Herds", "herd_name": name, "herd_class": herd_class,
		"min_weight_kg": min_kg, "max_weight_kg": max_kg, **extra,
	})
	return doc.insert(ignore_permissions=True)


def make_animal(herd, weight_kg=None, sex="Male", **extra):
	tag = "T" + frappe.generate_hash(length=8)
	doc = frappe.get_doc({
		"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": sex,
		"status": "Active", "current_herd": herd, **extra,
	}).insert(ignore_permissions=True)
	if weight_kg:
		submit_weight(doc.name, weight_kg)
	return doc


def submit_weight(animal, weight_kg, days_ago=0):
	doc = frappe.get_doc({
		"doctype": "Livestock Weight Record", "animal": animal,
		"weight_date": add_days(today(), -days_ago), "weight_kg": weight_kg,
	}).insert(ignore_permissions=True)
	doc.submit()
	return doc


def isolate(test):
	"""Undo everything this test creates when it ends, pass or fail.

	IntegrationTestCase only rolls back per class, so fixtures with fixed names
	would collide with the next test's."""
	frappe.db.rollback()
	frappe.db.savepoint("beef_test")

	def undo():
		try:
			frappe.db.rollback(save_point="beef_test")
		except Exception:
			# An endpoint's own error envelope rolls the whole transaction back,
			# taking the savepoint with it; nothing is left to undo.
			frappe.db.rollback()

	test.addCleanup(undo)


def move_animal(animal, new_herd, on=None):
	"""A submitted Movement event, dated `on` (default today). Backdated is fine
	here: the fixture writes the event directly, not through an endpoint."""
	from upande_livestock.serverscripts.common.events import new_livestock_event  # noqa: F401

	was = frappe.db.get_value("Animal", animal, "current_herd")
	doc = frappe.get_doc({
		"doctype": "Livestock Event", "event_type": "Movement", "animal": animal,
		"event_date": on or today(), "current_herd": was or "", "new_herd": new_herd,
		"operator": test_employee(), "remarks": "test move",
	})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def test_employee():
	"""Any Employee, made when the site has none (the operator is mandatory)."""
	name = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	if name:
		return name
	company = frappe.db.get_value("Company", {}, "name")
	return frappe.get_doc({
		"doctype": "Employee", "first_name": "ZZ Test", "gender": "Male", "company": company,
		"date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
	}).insert(ignore_permissions=True).name
