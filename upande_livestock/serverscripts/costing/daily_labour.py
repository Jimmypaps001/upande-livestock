# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One day's labour, ready to edit, and the days already entered.

The screen opens on a date. If that day was entered, its rows come back as
they were saved; if not, one blank row per category with the day rate from
Livestock Settings already in it, so on an ordinary day the feedlot manager
types the number of workers and nothing else.
"""

import frappe
from frappe.utils import getdate, today

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.costing import _data, _maths

#: How many earlier days the screen lists under the form.
RECENT = 14


@frappe.whitelist()
def daily_labour(date=None):
	def go():
		guard_read(_data.LABOUR_DOCTYPE)
		day = getdate(date or today())
		rates = _data.default_rates()
		name = frappe.db.get_value(_data.LABOUR_DOCTYPE, {"labour_date": day}, "name")
		if name:
			doc = frappe.get_doc(_data.LABOUR_DOCTYPE, name)
			rows = [
				{"category": r.category, "workers": r.workers, "day_rate": r.day_rate, "amount": r.amount,
				 "notes": r.notes or ""}
				for r in doc.entries
			]
			notes = doc.notes or ""
		else:
			rows = [
				{"category": c, "workers": 0, "day_rate": rates.get(c, 0), "amount": 0, "notes": ""}
				for c in _maths.LABOUR_CATEGORIES
			]
			notes = ""
		recent = frappe.get_all(
			_data.LABOUR_DOCTYPE,
			fields=["name", "labour_date", "total_workers", "total_amount"],
			order_by="labour_date desc",
			limit=RECENT,
		)
		return {
			"ok": True,
			"date": str(day),
			"saved": bool(name),
			"name": name,
			"rows": rows,
			"notes": notes,
			"categories": list(_maths.LABOUR_CATEGORIES),
			"default_rates": rates,
			"recent": [
				{"name": r.name, "date": str(r.labour_date), "workers": r.total_workers or 0,
				 "amount": float(r.total_amount or 0)}
				for r in recent
			],
			"can_write": bool(frappe.has_permission(_data.LABOUR_DOCTYPE, "write")),
		}

	return run(go, "livestock daily_labour failed")
