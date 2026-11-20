# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Milk Quality Test: one buyer's quality result for one batch of milk.

Posts nothing — no stock, no journal — so it is a plain record, not a
submittable one, and a result mis-keyed can simply be corrected. The rules live
in common/milk_quality_test so the endpoints and the tests share them.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from upande_livestock.serverscripts.common import milk_quality_test as mq

VALUE_FIELDS = (*mq.RANGES, *mq.CHOICES, "resazurin_score", "sensory_score")


class MilkQualityTest(Document):
	def validate(self):
		self.sample_date = mq.check_date(self.sample_date)
		values = mq.clean({f: self.get(f) for f in VALUE_FIELDS})
		if not mq.has_any_result(values):
			frappe.throw(_("Enter at least one result — a figure, a test outcome or a sensory score."))
		for field, value in values.items():
			if field in ("sample_type", "shift") and not value:
				value = self.get(field) if field == "shift" else "Bottle sample"
			self.set(field, value if value not in (None,) else None)
		if self.milk_recording and not frappe.db.exists("Milk Recording", self.milk_recording):
			frappe.throw(_("{0} is not a milk recording.").format(self.milk_recording))

		verdict = mq.evaluate(values)
		self.overall_result = verdict["overall"]
		self.failed_tests = ", ".join(verdict["failed"])
		self.aflatoxin_over_limit = 1 if verdict["checks"]["aflatoxin"] == "fail" else 0
		if not self.recorded_by:
			self.recorded_by = frappe.session.user
