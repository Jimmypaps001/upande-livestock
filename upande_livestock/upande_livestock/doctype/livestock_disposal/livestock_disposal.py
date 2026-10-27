# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Livestock Disposal controller.

On submit this both posts the asset accounting and permanently retires the
animal. The asset work is delegated to api/assets.py, which already handles
account resolution, the disposal Journal Entry / Sales Invoice and the Asset
status — this controller only decides which of the two entry points to call,
and downgrades any failure from that call to a warning.

scrap_livestock_asset() and sell_livestock_asset() already throw when the
animal has no linked Asset ("not capitalised") or the Asset is already
disposed — that failure is caught below rather than pre-checked, so the same
try/except path handles both "never an asset" and "already disposed", and an
uncapitalised animal is still recordable as dead or sold.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from upande_livestock.serverscripts.common import backdate, culling
from upande_livestock.serverscripts.common.animal import recompute_herd_count, retire_animal
from upande_livestock.serverscripts.common.gain import adg_between, weights_for, weights_for_many
from upande_livestock.serverscripts.common.withdrawal import withdrawal_warning
from upande_livestock.serverscripts.disposal.scrap_livestock_asset import (
	_scrap_livestock_asset,
	restore_scrapped_asset,
)
from upande_livestock.serverscripts.disposal.sell_livestock_asset import _sell_livestock_asset

SALE_TYPES = ("Sold",)
#: Exits whose gain over the animal's whole life is worth keeping.
EXIT_TYPES = ("Sold", "Slaughtered")


class LivestockDisposal(Document):
	def validate(self):
		# custom_is_backdated is read_only on the form only; a REST client can set it
		# alongside a date that is not in the past and collect the guard exemption and
		# the stock suppression it buys. Clear a claim the date does not support —
		# the flag stays stored, never derived, so this only ever unsets a false one.
		backdate.assert_not_future(self.disposal_date, "Disposal Date")
		backdate.sanitise(self, "disposal_date")
		if self.disposal_type in SALE_TYPES:
			self.price_the_sale()
		if self.disposal_type in EXIT_TYPES:
			self.set_final_adg()
			self.flags.warnings = self.withdrawal_warnings()

	def price_the_sale(self):
		"""A per-kg sale is worth its exit weight times the price per kg.

		The weight defaults to the latest weighing. With no price per kg the
		sale_price stays as typed — a cull case is priced by its approver.
		"""
		if flt(self.price_per_kg) <= 0:
			return
		if flt(self.exit_weight_kg) <= 0:
			points = weights_for_many([self.animal], birth=False)[self.animal]
			if not points:
				frappe.throw(_("{0} has no weighing to take an exit weight from. Enter the exit weight.").format(self.animal))
			self.exit_weight_kg = points[-1][1]
		self.sale_price = round(flt(self.exit_weight_kg) * flt(self.price_per_kg), 2)

	def set_final_adg(self):
		"""Lifetime ADG up to the exit, counting the exit weight as the last point."""
		on = getdate(self.disposal_date)
		points = [p for p in weights_for(self.animal) if p[0] <= on]
		if flt(self.exit_weight_kg) > 0 and (not points or points[-1][0] < on):
			points.append((on, flt(self.exit_weight_kg)))
		self.final_adg_kg = adg_between(points)

	def withdrawal_warnings(self):
		warning = withdrawal_warning(self.animal, self.disposal_date)
		return [warning] if warning else []

	def before_submit(self):
		# A cull case is submitted by post_cull once it is Approved. Submitting
		# one from the form while it waits on the vet or the manager retired the
		# animal and posted, and skipped both the review and the move to the
		# cull herd. A direct disposal (record_disposal) is Draft, and stays free.
		status = self.get("custom_review_status") or culling.DRAFT
		if status in (culling.AWAITING_VET, culling.AWAITING_APPROVAL, culling.REJECTED):
			frappe.throw(
				_("This cull case is {0}. It is posted from the Culling screen once approved.").format(status)
			)
		if self.disposal_type in SALE_TYPES and self.sale_price and not self.customer:
			# A buyer typed by name has no Customer to invoice, so the sale used to
			# post nothing and report success.
			frappe.throw(_("Choose the Customer the sale is invoiced to."))

	def on_submit(self):
		self.post_asset_disposal()
		retire_animal(self.animal, self.disposal_type)

	def on_cancel(self):
		"""Undo the disposal: postings first, then the animal.

		There was no on_cancel, and nothing links back to a disposal that would
		have stopped the cancel, so cancelling one left the animal retired and
		disabled, her herd count short, the write-off posted and the Asset
		Scrapped, the draft invoice standing, her move into the cull herd in
		place and the insurance claim open.
		"""
		self.reverse_asset_disposal()
		self.withdraw_draft_claims()
		self.undo_cull_herd_move()
		frappe.db.set_value("Animal", self.animal, {"status": "Active", "disabled": 0}, update_modified=False)
		recompute_herd_count(frappe.db.get_value("Animal", self.animal, "current_herd"))

	def reverse_asset_disposal(self):
		if self.sales_invoice and frappe.db.exists("Sales Invoice", self.sales_invoice):
			invoice = frappe.get_doc("Sales Invoice", self.sales_invoice)
			invoice.flags.ignore_permissions = True
			if invoice.docstatus == 0:
				invoice.delete(ignore_permissions=True)
				self.db_set("sales_invoice", None, update_modified=False)
			elif invoice.docstatus == 1:
				# ERPNext puts a sold fixed asset back in service when its invoice
				# is cancelled.
				invoice.cancel()
		asset = frappe.db.get_value("Animal", self.animal, "asset_link")
		if asset and self.writeoff_journal_entry:
			restore_scrapped_asset(asset)

	def withdraw_draft_claims(self):
		for name in frappe.get_all(
			"Livestock Insurance Claim", filters={"disposal": self.name, "docstatus": 0}, pluck="name"
		):
			frappe.delete_doc("Livestock Insurance Claim", name, ignore_permissions=True)

	def undo_cull_herd_move(self):
		"""Cancel the Movement post_cull made into the cull herd; it moves her back."""
		filters = {"animal": self.animal, "event_type": "Movement", "docstatus": 1,
		           "event_date": self.disposal_date, "new_herd": culling.CULL_HERD}
		for name in frappe.get_all("Livestock Event", filters=filters, pluck="name",
		                           order_by="creation desc", limit=1):
			move = frappe.get_doc("Livestock Event", name)
			move.flags.ignore_permissions = True
			move.cancel()

	def post_asset_disposal(self):
		"""Scrap or sell the linked Asset. Warn rather than throw on failure.

		A Sold disposal with no customer or no sale_price skips the sale posting
		with a warning rather than throwing: sell_livestock_asset() requires both,
		this site has no Customer records yet, and the disposal itself must still
		record and retire the animal. customer/sale_price stay optional fields —
		see livestock_disposal.json — with no mandatory_depends_on.
		"""
		# A backdated disposal records that the animal left and retires it, but posts
		# no money. _sell_livestock_asset raises a Sales Invoice and
		# _scrap_livestock_asset a write-off Journal Entry, both against a real ledger
		# — and neither is what the operator agreed to under the backdating banner,
		# which says in as many words that stocks are not being affected. The animal
		# is still retired by on_submit(); only the postings wait.
		#
		# A later reconciliation finds them with
		#     custom_is_backdated = 1 AND sales_invoice IS NULL AND writeoff_journal_entry IS NULL
		# — Livestock Disposal has no dedicated "unposted" flag either, and those two
		# link fields are filled by nothing but the postings skipped here.
		if self.get("custom_is_backdated"):
			frappe.msgprint(
				_("Backdated: the animal was retired, but no asset sale or write-off was posted."),
				alert=True,
				indicator="orange",
			)
			return

		if self.disposal_type in SALE_TYPES and not (self.customer and self.sale_price):
			frappe.msgprint(
				_("No Customer or sale price set, so the asset sale was not posted."),
				alert=True,
				indicator="orange",
			)
			return

		try:
			if self.disposal_type in SALE_TYPES:
				result = _sell_livestock_asset(
					animal=self.animal,
					customer=self.customer,
					selling_amount=self.sale_price,
					posting_date=self.disposal_date,
					exit_weight_kg=self.exit_weight_kg,
					price_per_kg=self.price_per_kg,
				)
				# A sale posts a Sales Invoice, not a Journal Entry. The old
				# sale_journal_entry field (Link -> Journal Entry) could never hold
				# this name, which is why it sat empty on every disposal ever made.
				if (result or {}).get("sales_invoice"):
					self.db_set("sales_invoice", result["sales_invoice"], update_modified=False)
			elif not frappe.db.get_value("Animal", self.animal, "asset_link"):
				# Nothing on the books to write off: a bull that was never
				# capitalised leaves with no posting, and no alert about one.
				return
			else:
				result = _scrap_livestock_asset(
					animal=self.animal,
					reason=self.disposal_type,
					scrapping_date=self.disposal_date,
				)
				if (result or {}).get("journal_entry"):
					self.db_set("writeoff_journal_entry", result["journal_entry"], update_modified=False)
		except Exception as e:
			frappe.log_error(message=frappe.get_traceback(), title="Livestock disposal asset error")
			frappe.msgprint(
				_("Asset postings failed and were skipped: {0}").format(str(e)),
				alert=True,
				indicator="orange",
			)
