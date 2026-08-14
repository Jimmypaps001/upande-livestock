# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from upande_livestock import livestock_stock
from upande_livestock.livestock_event_link import cancel_event_for, sync_event_for


class LivestockHealthCase(Document):
	def on_submit(self):
		sync_event_for(self, "Health Case")
		self.post_drug_issue()

	def on_cancel(self):
		cancel_event_for(self)

	def post_drug_issue(self):
		"""Issue the drugs recorded against this case's treatments.

		Each treatment row names a `drug_item` but carries no quantity — the field
		is `dosage`, free text like "20 ml", which cannot be trusted as a stock
		number. One unit per treatment row is issued instead, which keeps the drug
		store moving in step with treatments given without inventing a quantity from
		prose. Rows with no drug_item are skipped.

		Guarded by `self.drug_stock_entry` so re-submitting cannot double-issue.
		"""
		if self.drug_stock_entry:
			return

		warehouse = livestock_stock.drug_warehouse()
		rows = [
			{"item_code": t.drug_item, "qty": 1, "warehouse": warehouse}
			for t in (self.treatments or [])
			if t.drug_item
		]
		if not rows:
			return

		name = livestock_stock.try_issue_items(
			rows,
			remarks=f"Livestock Treatment - {self.animal} - {self.name}",
			what="Treatment",
			posting_date=self.opened_date,
			employee=self.opened_by,
		)
		if name:
			self.db_set("drug_stock_entry", name, update_modified=False)
