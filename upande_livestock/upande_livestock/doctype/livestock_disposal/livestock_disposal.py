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

from upande_livestock.serverscripts.common.animal import retire_animal
from upande_livestock.serverscripts.disposal.scrap_livestock_asset import scrap_livestock_asset
from upande_livestock.serverscripts.disposal.sell_livestock_asset import sell_livestock_asset

SALE_TYPES = ("Sold",)


class LivestockDisposal(Document):
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
		if self.disposal_type in SALE_TYPES and not (self.customer and self.sale_price):
			frappe.msgprint(
				_("No Customer or sale price set, so the asset sale was not posted."),
				alert=True,
				indicator="orange",
			)
			return

		try:
			if self.disposal_type in SALE_TYPES:
				result = sell_livestock_asset(
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
				result = scrap_livestock_asset(
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
