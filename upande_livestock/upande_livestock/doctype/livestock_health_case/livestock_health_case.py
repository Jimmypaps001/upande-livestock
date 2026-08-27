# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import flt, getdate, today

from upande_livestock import livestock_stock
from upande_livestock.livestock_event_link import cancel_event_for, sync_event_for


class LivestockHealthCase(Document):
	def on_submit(self):
		sync_event_for(self, "Health Case")
		self.post_drug_issue()

	def on_update_after_submit(self):
		# A case is treated over days, not once. Treatments are allow_on_submit so
		# the vet can add today's round to an open case, and each new row issues
		# when it is added.
		self.post_drug_issue()

	def on_cancel(self):
		cancel_event_for(self)

	def post_drug_issue(self):
		"""Issue the drugs recorded against this case's treatments.

		Each treatment row carries its own `qty` in the drug's stock UOM. That is
		a separate field from `dosage`, which is the clinical instruction ("20 ml")
		and free text — this used to issue a hardcoded 1 per row because there was
		nowhere to put a real number, which kept the store moving but made every
		quantity wrong. Rows with no drug_item are skipped; a row with a drug and
		no qty issues one unit rather than nothing.

		Blocks when the store cannot cover the treatments — see livestock_stock.

		The guard is per row, not per case: a case is treated over days, so a
		single `drug_stock_entry` flag on the parent would let the first round
		issue and silently swallow every round after it. Each row remembers its
		own Stock Entry, and only rows without one are issued.
		"""
		warehouse = livestock_stock.drug_warehouse()
		pending = [t for t in (self.treatments or []) if t.drug_item and not t.stock_entry_ref]
		if not pending:
			return

		rows = [
			{"item_code": t.drug_item, "qty": flt(t.get("qty")) or 1, "warehouse": warehouse}
			for t in pending
		]
		# Post on the day the treatment was given, not the day the case opened. A
		# case opened before its drug was even delivered would otherwise back-date
		# the issue into a period where the store held none of it.
		given = max(
			[getdate(t.treatment_date) for t in pending if t.treatment_date] or [getdate(today())]
		)
		name = livestock_stock.issue_items(
			rows,
			remarks=f"Livestock Treatment - {self.animal} - {self.name}",
			what="Treatment",
			posting_date=given,
			employee=self.opened_by,
		)
		if name:
			for t in pending:
				t.db_set("stock_entry_ref", name, update_modified=False)
			self.db_set("drug_stock_entry", name, update_modified=False)
