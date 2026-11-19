# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

#: One record per herd and day: the day's actuals are one fact, and two
#: records for it would let the report and the mixer disagree about it.
UNIQUE_FIELDS = ["date", "herd"]
UNIQUE_CONSTRAINT = "unique_feed_actual_day"


class LivestockFeedActual(Document):
	"""A herd's feed day: the recipe's plan beside what was actually fed.

	Written by `serverscripts/feeding/feed_actuals.py`. Moves no stock itself;
	manufacturing the actuals does that through the feeding engine and links
	the Work Order and Stock Entries back here.
	"""

	def validate(self):
		clash = frappe.db.get_value(
			self.doctype, {"date": self.date, "herd": self.herd, "name": ["!=", self.name]}, "name")
		if clash:
			frappe.throw(_("{0} already has a feed day for {1} ({2}).").format(self.herd, self.date, clash))
		self.planned_kg = flt(sum(flt(r.planned_kg) for r in self.items), 3)
		self.actual_kg = flt(sum(flt(r.actual_kg) for r in self.items), 3)
		self.amended = 1 if any(abs(flt(r.actual_kg) - flt(r.planned_kg)) > 1e-6 for r in self.items) else 0
		if self.status in (None, "", "Planned", "Amended"):
			self.status = "Amended" if self.amended else "Planned"


def on_doctype_update():
	frappe.db.add_unique("Livestock Feed Actual", UNIQUE_FIELDS, constraint_name=UNIQUE_CONSTRAINT)
