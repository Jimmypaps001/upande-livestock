# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Find an existing Customer to sell an animal to."""

import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run


@frappe.whitelist()
def buyer_search(payload=None):
	"""Customers matching a typed name, phone or KRA PIN, enabled ones only.

	Read-guarded on Livestock Disposal and answered with ignore_permissions: the
	people who sell an animal are not given the Customer list, and this returns only
	the few fields the picker shows."""

	def go():
		guard_read("Livestock Disposal")
		term = (as_dict(payload).get("term") or "").strip()
		like = "%" + term + "%"
		rows = frappe.db.sql(
			"""SELECT name, customer_name, customer_type, tax_id, mobile_no, payment_terms
			   FROM `tabCustomer`
			   WHERE disabled = 0 AND (%(t)s = '' OR name LIKE %(like)s OR customer_name LIKE %(like)s
			         OR mobile_no LIKE %(like)s OR tax_id LIKE %(like)s)
			   ORDER BY (name LIKE %(start)s) DESC, modified DESC
			   LIMIT 20""",
			{"t": term, "like": like, "start": term + "%"}, as_dict=True,
		)
		return {"ok": True, "buyers": rows}

	return run(go, "livestock buyer_search failed")
