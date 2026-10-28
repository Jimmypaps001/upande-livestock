# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Save a buyer commitment: the orders the forecast is covered against."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, guard_write, run
from upande_livestock.serverscripts.forecast import data

DOCTYPE = data.COMMITMENT_DOCTYPE
FIELDS = data.COMMITMENT_FIELDS


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
