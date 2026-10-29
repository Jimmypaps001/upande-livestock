"""The herd a test files its cow in.

Kaitet's tests name "Breeding Cows"; a beef site (Mutara) has no herd of that name. Use it
where it exists, else the first Breeding-class herd, so the tests run on either farm."""

import frappe

KAITET_HERD = "Breeding Cows"


def cow_herd():
	if frappe.db.exists("Herds", KAITET_HERD):
		return KAITET_HERD
	return (
		frappe.db.get_value("Herds", {"herd_class": "Breeding"}, "name", order_by="name asc")
		or frappe.db.get_value("Herds", {}, "name", order_by="name asc")
	)
