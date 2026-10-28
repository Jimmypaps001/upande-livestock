# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate


class LivestockBuyerCommitment(Document):
	"""A buyer's standing order for finished animals in one delivery week.

	The forecast sets what the farm expects to have ready each week against
	these Open commitments; Fulfilled and Cancelled ones drop out of the cover.
	"""

	def validate(self):
		if self.week_start:
			day = getdate(self.week_start)
			self.week_start = add_days(day, -day.weekday())  # ISO weeks start on Monday
		if (self.head or 0) <= 0:
			frappe.throw(_("Head must be greater than 0."))
		if (self.committed_kg or 0) < 0 or (self.min_weight_kg or 0) < 0:
			frappe.throw(_("Weights cannot be negative."))
