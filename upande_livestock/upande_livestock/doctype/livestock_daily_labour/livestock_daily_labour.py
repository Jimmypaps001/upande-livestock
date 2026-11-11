# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class LivestockDailyLabour(Document):
	"""One day's labour: workers × day rate per category.

	The rows are cleaned by `costing._maths.labour_lines` — the same function
	the web screen's endpoint relies on — so a day typed on the desk and a day
	saved from the phone come out the same: a blank rate takes the category's
	default from Livestock Settings, the amount is always workers × rate (never
	typed), and rows with no workers are dropped.
	"""

	def validate(self):
		from upande_livestock.serverscripts.costing import _data, _maths

		if self.labour_date and getdate(self.labour_date) > getdate(today()):
			frappe.throw(_("Labour cannot be entered for a day that has not happened yet."))
		try:
			lines = _maths.labour_lines([r.as_dict() for r in self.entries], _data.default_rates())
		except ValueError as e:
			frappe.throw(_(str(e)))
		self.set("entries", [])
		for line in lines:
			self.append("entries", line)
		self.total_workers = sum(line["workers"] for line in lines)
		self.total_amount = sum(line["amount"] for line in lines)
