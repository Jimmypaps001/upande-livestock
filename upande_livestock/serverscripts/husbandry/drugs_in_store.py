"""What the drug store currently holds.

Read-guarded on Item — this discloses stock balances."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.husbandry._shared import husbandry_drug_items


@frappe.whitelist()
def drugs_in_store():
	"""The drug picker, with the balances of the store each drug is actually in.

	No store to name: each choice carries the `warehouse` its stock is mostly in
	and every store holding any in `locations`, so the quantities on screen
	describe the shelf the issue will come off.
	"""

	def go():
		guard_read("Item")
		return {"ok": True, "drug_items": husbandry_drug_items()}

	return run(go, "livestock drugs_in_store failed")
