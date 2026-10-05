# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate, today

from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common import cost_center as livestock_cost_center
from upande_livestock.serverscripts.common import event_items
from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.common.event_link import cancel_event_for, stamp_stock_entry, sync_event_for

#: The event type whose stock rule a case's treatments follow.
TREATMENT = "Treatment"


class LivestockHealthCase(Document):
	def validate(self):
		# custom_is_backdated is read_only on the form only; a REST client can set it
		# alongside a date that is not in the past and collect the guard exemption and
		# the stock suppression it buys. Clear a claim the date does not support —
		# the flag stays stored, never derived, so this only ever unsets a false one.
		backdate.assert_not_future(self.opened_date, "Opened Date")
		backdate.sanitise(self, "opened_date")
		self.recompute_treatment_cost()
		self.recompute_milk_safe_date()
		self.require_named_drugs()

	def recompute_treatment_cost(self):
		"""The case has cost the sum of its treatments, and nothing else.

		`total_treatment_cost` is read_only and was never assigned by anything,
		so the Health page's tile counted zeroes for every case on the farm.
		Recomputed rather than incremented: a treatment removed has to take its
		cost with it.
		"""
		self.total_treatment_cost = flt(
			sum(flt(t.get("cost")) for t in (self.treatments or []))
		)

	def on_submit(self):
		sync_event_for(self, "Health Case")
		self.post_drug_issue()

	def before_update_after_submit(self):
		"""Treatments are added to a case that is ALREADY submitted.

		Frappe runs `validate` only for `_action in ("save", "submit")`; a doc
		that is saved again at docstatus 1 takes the `update_after_submit`
		branch, which runs this and not `validate`. Both doors that add a
		treatment — `treat_animal` and `add_case_treatment` — arrive here, so a
		roll-up hung only off `validate` fired twice per case, at insert and at
		submit, with the treatments table empty both times. The total was
		written as 0.0 and never touched again.

		Not `on_update_after_submit`: that runs AFTER `db_update()`, so the
		assignment would never reach the row.
		"""
		self.recompute_treatment_cost()
		self.recompute_milk_safe_date()
		self.require_named_drugs()

	def require_named_drugs(self):
		"""Each treatment names its drug, where the Treatment event type says it
		must. A drug typed only as text cannot be issued or costed."""
		if not event_items.must_name_item(TREATMENT) or self.get("custom_is_backdated"):
			return
		if any(not t.drug_item for t in self.treatments or []):
			frappe.throw(_("Each treatment must name the drug it used, picked from the store."),
			             title=_("Drug required"))

	def recompute_milk_safe_date(self):
		"""The first day her milk may be sold again, from the drugs she was given.

		Each treatment carries its drug's withdrawal period, and nothing ever
		turned them into a date: the case file showed "—" and staff counted
		forward by hand. The latest treatment date plus its withdrawal wins.
		"""
		ends = [
			add_days(getdate(t.treatment_date), int(t.withdrawal_period_days))
			for t in (self.treatments or [])
			if t.get("treatment_date") and t.get("withdrawal_period_days")
		]
		self.milk_safe_date = max(ends) if ends else None

	def on_update_after_submit(self):
		# A case is treated over days, not once. Treatments are allow_on_submit so
		# the vet can add today's round to an open case, and each new row issues
		# when it is added.
		self.post_drug_issue()

	def on_cancel(self):
		cancel_event_for(self)
		# The drugs go back on the shelf. Only the timeline event was cancelled,
		# so a cancelled case kept the store short of everything it issued.
		entries = {self.drug_stock_entry} | {t.stock_entry_ref for t in self.treatments or []}
		livestock_stock.cancel_issues(entries)

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

		A backdated case records its treatments without moving stock: the rows
		and their quantities stay on the case for a later reconciliation, but the
		store's balance is not rewritten for a treatment given months ago.
		"""
		# The store each treatment names, not one for the whole case. On live
		# `drug_warehouse()` is `Livestock Drug Store - KR`, which holds nothing
		# — so every treatment asked an empty shelf while the drugs sat in
		# Drug/Medicine Store - Old Office, Westwood Dairy Store and General
		# Store Karen. The fallback stays for rows recorded before this.
		if not event_items.consumes_items(TREATMENT):
			return
		default_wh = event_items.default_store(TREATMENT)
		pending = [t for t in (self.treatments or []) if t.drug_item and not t.stock_entry_ref]
		# A backdated case records its old treatments without moving stock, but
		# only the old ones: a round added today to a case opened late is given
		# today and is issued like any other.
		if self.get("custom_is_backdated"):
			pending = [t for t in pending if t.treatment_date and getdate(t.treatment_date) >= getdate(today())]
		# One issue per day given. Rows from Oct 1 and Oct 5 saved together used
		# to post as one entry, both on Oct 5.
		by_day = {}
		for t in pending:
			by_day.setdefault(getdate(t.treatment_date or today()), []).append(t)
		for given, rows_of_day in sorted(by_day.items()):
			self._issue_round(rows_of_day, given, default_wh)

	def _issue_round(self, pending, given, default_wh):
		rows = [
			{
				"item_code": t.drug_item,
				"qty": flt(t.get("qty")) or 1,
				"warehouse": t.get("source_warehouse") or default_wh,
				"batch_no": t.get("batch_no"),
			}
			for t in pending
		]
		# Posted on the day the treatment was given, not the day the case opened,
		# and under the animal's company rather than Livestock Settings' default.
		name = livestock_stock.issue_items(
			rows,
			remarks=f"Livestock Treatment - {self.animal} - {self.name}",
			what="Treatment",
			posting_date=given,
			employee=self.opened_by,
			company=self.company,
			# A case is one animal, so its herd is unambiguous. Charged there
			# rather than to whatever the company default happens to be.
			herd=livestock_cost_center.herd_of(self.animal),
		)
		if name:
			for t in pending:
				t.db_set("stock_entry_ref", name, update_modified=False)
			self.db_set("drug_stock_entry", name, update_modified=False)
			stamp_stock_entry(self, name)
