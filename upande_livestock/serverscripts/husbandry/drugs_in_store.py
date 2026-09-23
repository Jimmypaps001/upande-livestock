"""What the drug store currently holds.

Read-guarded on Item — this discloses stock balances."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.stock_items import stock_items
from upande_livestock.serverscripts.common import stock as livestock_stock


@frappe.whitelist()
def drugs_in_store(warehouse=None):
	"""The drug picker, with the balances of the store each drug is actually in.

	Called when the user changes the store, so the quantities on screen always
	describe the shelf the issue will come off. Called with no store to search
	every configured one, which is what the pickers do on first load.
	"""

	def go():
		guard_read("Item")
		# A named store narrows to it; without one every configured drug store
		# is searched and each choice carries the store its stock is in.
		return {
			"ok": True,
			"warehouse": warehouse,
			"warehouses": livestock_stock.drug_source_warehouses(),
			"drug_items": stock_items("drug", warehouse),
		}

	return run(go, "livestock drugs_in_store failed")
