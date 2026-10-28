# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""List buyer commitments, optionally by status and from a week on."""

import frappe
from frappe.utils import getdate

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.forecast import data, engine


@frappe.whitelist()
def list_buyer_commitments(status=None, from_week=None) -> list:
	guard_read(data.COMMITMENT_DOCTYPE)
	filters = {}
	if status:
		filters["status"] = status
	if from_week:
		filters["week_start"] = [">=", engine.iso_week_start(getdate(from_week))]
	rows = frappe.get_all(
		data.COMMITMENT_DOCTYPE,
		filters=filters,
		fields=["name", *data.COMMITMENT_FIELDS],
		order_by="week_start asc, creation asc",
	)
	return [{**r, "week_start": str(r["week_start"]) if r["week_start"] else None} for r in rows]
