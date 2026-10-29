# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""N animals weighed, their average: the herd's live weight comes from the newest of these."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, today

from upande_livestock.serverscripts.common import shoats


class HerdWeightSample(Document):
	def validate(self):
		if not shoats.is_by_number(self.herd):
			frappe.throw(_("{0} is not counted by number.").format(self.herd))
		if getdate(self.sample_date) > getdate(today()):
			frappe.throw(_("The date cannot be in the future."))
		if self.sample_class not in shoats.SAMPLE_CLASSES:
			frappe.throw(_("Class must be one of: {0}.").format(", ".join(shoats.SAMPLE_CLASSES)))
		n, avg = cint(self.animals_weighed), flt(self.average_kg)
		if n <= 0:
			frappe.throw(_("Say how many animals were weighed."))
		if not 0 < avg <= 200:
			frappe.throw(_("The average weight must be between 0 and 200 kg."))
		hd = shoats.head_on(self.herd, self.sample_date)
		pool = hd["total"] if self.sample_class == "All" else hd[self.sample_class]
		if n > pool:
			frappe.throw(_("{0} animals weighed, but {1} only had {2} on {3}.").format(
				n, self.herd, pool, frappe.utils.formatdate(self.sample_date)))
		self.total_kg = round(n * avg, 1)
