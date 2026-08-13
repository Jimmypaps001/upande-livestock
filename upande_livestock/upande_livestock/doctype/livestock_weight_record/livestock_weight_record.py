# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Livestock Weight Record controller.

Closes a real gap: Animal.last_weight_kg and Animal.last_bcs existed on the
Animal doctype but nothing ever wrote to them, because this doctype was an empty
scaffold.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt, getdate, today


class LivestockWeightRecord(Document):
	def validate(self):
		if flt(self.weight_kg) <= 0:
			frappe.throw(_("Weight must be greater than zero."))

		if getdate(self.weight_date) > getdate(today()):
			frappe.throw(_("Weight Date cannot be in the future."))

		self.set_previous_weight()

	def set_previous_weight(self):
		"""Fill previous weight and average daily gain from the prior submitted record."""
		self.previous_weight_kg = None
		self.previous_weight_date = None
		self.daily_gain_kg = 0

		previous = frappe.db.sql(
			"""SELECT weight_kg, weight_date
			   FROM `tabLivestock Weight Record`
			   WHERE animal = %(animal)s
			     AND docstatus = 1
			     AND name != %(name)s
			     AND weight_date <= %(weight_date)s
			   ORDER BY weight_date DESC, creation DESC
			   LIMIT 1""",
			{"animal": self.animal, "name": self.name or "new", "weight_date": self.weight_date},
			as_dict=True,
		)
		if not previous:
			return

		self.previous_weight_kg = previous[0].weight_kg
		self.previous_weight_date = previous[0].weight_date

		days = date_diff(self.weight_date, previous[0].weight_date)
		if days > 0:
			self.daily_gain_kg = (flt(self.weight_kg) - flt(previous[0].weight_kg)) / days

	def on_submit(self):
		self.update_animal_snapshot()

	def update_animal_snapshot(self):
		values = {"last_weight_kg": flt(self.weight_kg)}
		if self.bcs:
			values["last_bcs"] = flt(self.bcs)
		frappe.db.set_value("Animal", self.animal, values, update_modified=False)
