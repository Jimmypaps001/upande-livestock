# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from upande_livestock.livestock_event_link import cancel_event_for, sync_event_for


class LivestockHealthCase(Document):
	def on_submit(self):
		sync_event_for(self, "Health Case")

	def on_cancel(self):
		cancel_event_for(self)
