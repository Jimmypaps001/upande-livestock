# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

#: One record per herd and day: cost per animal adds a history day's cost to its
#: herd, so a second record for the same day would count that day's feed twice.
UNIQUE_FIELDS = ["date", "herd"]
UNIQUE_CONSTRAINT = "unique_feed_history_day"


class LivestockFeedHistory(Document):
	"""What a herd ate on a day before the farm fed through the app — history only.

	Deliberately has no submit, no stock hooks and no accounting: the feed was
	never received into the system, so posting it would invent stock and money
	nobody moved. Cost per animal reads `total_cost` only for a herd-day with no
	feed issue in the stock ledger (`costing._maths.merge_feed`).
	"""

	def validate(self):
		clash = frappe.db.get_value(
			self.doctype, {"date": self.date, "herd": self.herd, "name": ["!=", self.name]}, "name")
		if clash:
			frappe.throw(_("{0} already has feed history for {1} ({2}).").format(self.herd, self.date, clash))
		for row in self.items:
			row.amount = flt(flt(row.qty_kg) * flt(row.rate), 2)
		self.total_kg = flt(sum(flt(r.qty_kg) for r in self.items), 3)
		# The tracker's own cost wins: it is what the farm's books carried that day.
		if not flt(self.total_cost):
			self.total_cost = flt(sum(flt(r.amount) for r in self.items), 2)


def on_doctype_update():
	"""The database's own guard on one record per herd and day, beneath the friendlier check in validate."""
	frappe.db.add_unique("Livestock Feed History", UNIQUE_FIELDS, constraint_name=UNIQUE_CONSTRAINT)
