# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import flt

from upande_livestock import livestock_stock
from upande_livestock.livestock_event_link import cancel_event_for, sync_event_for


class LivestockDiagnosis(Document):
	def on_submit(self):
		sync_event_for(self, "Check Up")
		self.post_drug_issue()

	def on_cancel(self):
		cancel_event_for(self)

	def post_drug_issue(self):
		"""Issue anything given at the check out of the drug store.

		A routine check that turns into a treatment used to move no stock at all —
		the form had "Action taken" and nowhere to name a drug. Rows with no item
		are skipped, so a check that treats nothing posts nothing.

		Blocks when the store cannot cover it, and is guarded by `self.stock_entry`
		so an amend cannot double-issue.
		"""
		if self.stock_entry:
			return

		default_wh = livestock_stock.drug_warehouse()
		rows = [
			{
				"item_code": row.item_code,
				"qty": flt(row.qty) or 1,
				"warehouse": row.source_warehouse or default_wh,
				"batch_no": row.batch_no,
				"uom": row.uom,
			}
			for row in (self.drug_issues or [])
			if row.item_code
		]
		if not rows:
			return

		name = livestock_stock.issue_items(
			rows,
			remarks=f"Livestock Check Up - {self.animal} - {self.name}",
			posting_date=self.diagnosis_date,
			employee=self.operator,
		)
		if name:
			self.db_set("stock_entry", name, update_modified=False)
			for row in self.drug_issues or []:
				if row.item_code:
					row.db_set("stock_entry_ref", name, update_modified=False)
