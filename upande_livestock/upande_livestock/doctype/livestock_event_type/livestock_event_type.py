# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockEventType(Document):
	def on_update(self):
		# An event set to post stock posts it under its own name.
		if self.get("posts_stock_entry"):
			from upande_livestock.serverscripts.common.stock import ensure_event_stock_entry_type

			ensure_event_stock_entry_type(self.name)
