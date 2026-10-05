# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import flt


class LivestockInsurancePolicy(Document):
	def validate(self):
		# Read-only on the form and computed by nothing, so it only ever held
		# what somebody typed. It is the sum of the animals covered.
		self.total_insured_value = sum(flt(row.insured_value) for row in self.animals)
