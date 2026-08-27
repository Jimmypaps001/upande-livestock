# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Animal(Document):
	def on_update(self):
		# Recompute Herd headcount when an Animal is created/updated.
		# (Movement events are handled in LivestockEvent; this covers direct edits.)
		# Ported from the "Number of animals in a Herd" Server Script.
		self._recount(self.get("current_herd"))

		# An edit that moves the animal between herds leaves the OLD herd one
		# too many. get_doc_before_save() is the only place the previous value
		# still exists by the time this runs.
		before = self.get_doc_before_save()
		if before and before.get("current_herd") and before.current_herd != self.get("current_herd"):
			self._recount(before.current_herd)

	def after_delete(self):
		# Nothing recomputed on delete, so a deleted animal stayed in its herd's
		# headcount for good — and the feeding programme went on manufacturing a
		# ration for it. Runs after the row is gone so the count is the new one.
		self._recount(self.get("current_herd"))

	@staticmethod
	def _recount(herd):
		if not herd:
			return
		# One definition of "in this herd", in api.animal — a second copy here
		# is how the count and the disposal path drifted apart before.
		from upande_livestock.api.animal import recompute_herd_count

		recompute_herd_count(herd)
