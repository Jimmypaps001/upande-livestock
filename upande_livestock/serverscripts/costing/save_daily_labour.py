# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Save one day's labour: {date, rows: [{category, workers, day_rate?, notes?}], notes?}.

One Livestock Daily Labour per date, so saving a day that already has one
replaces its rows rather than adding a second record the report would count
twice. A new day is guarded on create, an existing one on write — the same
pair `forecast/save_buyer_commitment` uses.

The manager's office entry, not a record made in the yard, so no linked
Employee is required (`employee=False`), as for the other manager-only books.
Rates and amounts are worked out by the document itself (`_maths.labour_lines`
from its validate), so the page, the desk form and this endpoint all agree.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard, guard_write, run
from upande_livestock.serverscripts.costing import _data


@frappe.whitelist()
def save_daily_labour(payload):
	def go():
		data = as_dict(payload)
		day = getdate(data.get("date") or today())
		if day > getdate(today()):
			frappe.throw(_("Labour cannot be entered for a day that has not happened yet."))
		rows = data.get("rows") or []
		if not isinstance(rows, list):
			frappe.throw(_("The labour rows did not arrive as a list."))
		name = frappe.db.get_value(_data.LABOUR_DOCTYPE, {"labour_date": day}, "name")
		if name:
			guard_write(_data.LABOUR_DOCTYPE)
			doc = frappe.get_doc(_data.LABOUR_DOCTYPE, name)
		else:
			guard(_data.LABOUR_DOCTYPE, employee=False)
			doc = frappe.new_doc(_data.LABOUR_DOCTYPE)
			doc.labour_date = day
		doc.notes = (data.get("notes") or "").strip()
		doc.set("entries", [])
		for r in rows:
			if not isinstance(r, dict):
				continue
			doc.append("entries", {
				"category": r.get("category"),
				"workers": r.get("workers") or 0,
				# Blank, not 0: a blank rate takes the category default in validate.
				"day_rate": None if r.get("day_rate") in (None, "") else r.get("day_rate"),
				"notes": r.get("notes") or "",
			})
		doc.save()
		return {
			"ok": True,
			"name": doc.name,
			"date": str(doc.labour_date),
			"total_workers": doc.total_workers,
			"total_amount": float(doc.total_amount or 0),
		}

	return run(go, "livestock save_daily_labour failed")
