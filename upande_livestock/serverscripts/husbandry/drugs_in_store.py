"""What the drug store currently holds.

Read-guarded on Item — this discloses stock balances."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.stock_items import stock_items
from upande_livestock.serverscripts.common import stock as livestock_stock


@frappe.whitelist()
def drugs_in_store(warehouse=None):
	"""The drug picker for one store, with that store's balances.

	Called when the user changes the store, so the quantities on screen always
	describe the shelf the issue will come off.
	"""

	def go():
		guard_read("Item")
		wh = warehouse or livestock_stock.drug_warehouse()
		return {"ok": True, "warehouse": wh, "drug_items": stock_items("drug", wh)}

	return run(go, "livestock drugs_in_store failed")
