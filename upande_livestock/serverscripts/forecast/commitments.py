# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Buyer commitments: save and list the orders the forecast is covered against."""

import frappe
from frappe import _
from frappe.utils import getdate

from upande_livestock.serverscripts.common.envelope import as_dict, guard, guard_read, guard_write, run

DOCTYPE = "Livestock Buyer Commitment"
FIELDS = ("customer", "week_start", "head", "min_weight_kg", "committed_kg", "price_per_kg", "status", "notes")


@frappe.whitelist()
def save_buyer_commitment(payload) -> dict:
	"""Create a commitment, or update the one named by `payload["name"]`."""

	def _do():
		data = as_dict(payload)
		name = data.get("name")
		values = {f: data[f] for f in FIELDS if f in data}
		if name:
			guard_write(DOCTYPE)
			doc = frappe.get_doc(DOCTYPE, name)
			doc.update(values)
			doc.save()
		else:
			guard(DOCTYPE, employee=False)
			doc = frappe.get_doc({"doctype": DOCTYPE, **values})
			doc.insert()
		return {"ok": True, "name": doc.name}

	return run(_do, _("Save buyer commitment"))


@frappe.whitelist()
def list_buyer_commitments(status=None, from_week=None) -> list:
	guard_read(DOCTYPE)
	filters = {}
	if status:
		filters["status"] = status
	if from_week:
		filters["week_start"] = [">=", getdate(from_week)]
	rows = frappe.get_all(
		DOCTYPE,
		filters=filters,
		fields=["name", *FIELDS],
		order_by="week_start asc, creation asc",
	)
	return [{**r, "week_start": str(r["week_start"]) if r["week_start"] else None} for r in rows]
