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

from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common.animal import retire_animal
from upande_livestock.serverscripts.disposal.scrap_livestock_asset import _scrap_livestock_asset
from upande_livestock.serverscripts.disposal.sell_livestock_asset import _sell_livestock_asset

SALE_TYPES = ("Sold",)


class LivestockDisposal(Document):
	def validate(self):
		# custom_is_backdated is read_only on the form only; a REST client can set it
		# alongside a date that is not in the past and collect the guard exemption and
		# the stock suppression it buys. Clear a claim the date does not support —
		# the flag stays stored, never derived, so this only ever unsets a false one.
		backdate.assert_not_future(self.disposal_date, "Disposal Date")
		backdate.sanitise(self, "disposal_date")

	def on_submit(self):
		self.post_asset_disposal()
		retire_animal(self.animal, self.disposal_type)

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
				)
				# A sale posts a Sales Invoice, not a Journal Entry. The old
				# sale_journal_entry field (Link -> Journal Entry) could never hold
				# this name, which is why it sat empty on every disposal ever made.
				if (result or {}).get("sales_invoice"):
					self.db_set("sales_invoice", result["sales_invoice"], update_modified=False)
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
