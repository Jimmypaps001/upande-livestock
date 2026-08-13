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
		"""Fill previous weight and average daily gain from the prior submitted record.

		These are computed once, at entry, from whatever prior records exist at
		that moment. They are deliberately NOT recomputed later: if a sibling
		record referenced here is subsequently cancelled, or a new record is
		backdated in between this one and what was its previous record, this
		record's previous_weight_kg / previous_weight_date / daily_gain_kg go
		stale. Treat them as a snapshot taken at save time, not a live value.
		"""
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
			{"animal": self.animal, "name": self.name, "weight_date": self.weight_date},
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

	def on_cancel(self):
		self.update_animal_snapshot()

	def update_animal_snapshot(self):
		"""Set Animal.last_weight_kg/last_bcs from the chronologically latest
		submitted weight record for this animal — not necessarily self.

		Deriving the snapshot from a fresh lookup (rather than writing self's
		own values) is what makes this correct regardless of entry order: a
		backdated record submitted after a more recent one must not regress
		the snapshot, and cancelling the latest record must fall back to
		whatever is now the latest remaining one. Both on_submit and on_cancel
		call this same method for that reason. By the time either fires, this
		document's own docstatus change has already been written to the
		database (db_update happens before run_post_save_methods), so the
		docstatus = 1 filter below naturally includes self on submit and
		excludes self on cancel without any special-casing.

		If no submitted record remains for the animal (e.g. every record has
		been cancelled), the snapshot is left untouched rather than zeroed —
		zeroing would assert the animal weighs nothing, which is never true.
		"""
		latest = frappe.db.sql(
			"""SELECT weight_kg, bcs
			   FROM `tabLivestock Weight Record`
			   WHERE animal = %(animal)s
			     AND docstatus = 1
			   ORDER BY weight_date DESC, creation DESC
			   LIMIT 1""",
			{"animal": self.animal},
			as_dict=True,
		)
		if not latest:
			return

		values = {"last_weight_kg": flt(latest[0].weight_kg)}
		if latest[0].bcs:
			values["last_bcs"] = flt(latest[0].bcs)
		frappe.db.set_value("Animal", self.animal, values, update_modified=False)
