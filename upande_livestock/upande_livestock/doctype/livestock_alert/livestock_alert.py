# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now


class LivestockAlert(Document):
	"""Something about an animal that somebody should look at.

	Raised by serverscripts.alerts.raise_alerts on a schedule, one per animal per kind
	per day. It records WHAT should be said; how it reaches a person is not
	decided here, so nothing in this doctype sends anything.
	"""

	def validate(self):
		# Stamp who closed it, so "actioned" is attributable rather than a flag
		# somebody flipped.
		if self.status and self.status != "Open" and not self.actioned_on:
			self.actioned_on = now()
			self.actioned_by = frappe.session.user
		if self.status == "Open":
			self.actioned_on = None
			self.actioned_by = None
