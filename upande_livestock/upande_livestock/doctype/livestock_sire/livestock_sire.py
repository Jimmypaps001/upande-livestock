# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A bull the herd is bred to: an AI straw's sire or a live bull.

Named by the bull's registration code when it has one (NL734970583), else by its
name, so two records can never be the same bull. Services and calves link here
instead of carrying the bull as free text; the text stays beside the link for
the old records and for the phone.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from upande_livestock.serverscripts.common import livestock_sire as LS


class LivestockSire(Document):
	def autoname(self):
		# Runs before validate, so the code is tidied here too.
		self.sire_code = LS.tidy(self.sire_code).upper() or None
		self.name = self.sire_code or LS.tidy(self.sire_name)
		self.check_unique_code()
		if frappe.db.exists("Livestock Sire", self.name):
			frappe.throw(_("{0} is already a sire.").format(self.name), title=_("Duplicate sire"))

	def validate(self):
		self.sire_name = LS.tidy(self.sire_name)
		code = LS.tidy(self.sire_code).upper()
		self.sire_code = code or None
		if not self.sire_name:
			frappe.throw(_("Sire Name is required."))
		self.display_name = LS.label(self.sire_name, self.sire_code)
		self.check_unique_code()
		if self.sire_type == "Semen":
			self.animal = None
		elif self.sire_type == "Live bull":
			self.semen_item = None
			self.sexed = 0

	def check_unique_code(self):
		if not self.sire_code:
			return
		other = frappe.db.get_value(
			"Livestock Sire", {"sire_code": self.sire_code, "name": ("!=", self.name)}, "name"
		)
		if other:
			frappe.throw(
				_("Sire code {0} already belongs to {1}.").format(self.sire_code, other),
				title=_("Duplicate sire code"),
			)
