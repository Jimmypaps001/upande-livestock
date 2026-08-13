# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Animal(Document):
	def on_update(self):
		# Recompute Herd headcount when an Animal is created/updated.
		# (Movement events are handled in LivestockEvent; this covers direct edits.)
		# Ported from the "Number of animals in a Herd" Server Script.
		current_herd = self.get("current_herd")
		if current_herd:
			cnt = frappe.db.count("Animal", {"current_herd": current_herd, "docstatus": ["!=", 2]})
			frappe.db.set_value("Herds", current_herd, "number_of_animals", cnt)
