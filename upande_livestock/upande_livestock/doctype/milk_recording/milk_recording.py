# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class MilkRecording(Document):
	def validate(self):
		# The whole point of a milk record is the amount milked. Frappe's `reqd`
		# lets a numeric 0 through, so guard the actual value: no record may be
		# saved/submitted without a positive yield for the herd milked.
		if flt(self.total_yield_kg) <= 0:
			frappe.throw(
				"Enter the amount of milk produced (Total Yield must be greater than 0)."
			)
