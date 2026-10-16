# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The livestock stores' stock, read-only, for the handset's Stock list.

Field roles cannot read Bin, which is why the pickers get their quantities
through `items_by_event`. This is the same read, shaped as a browsable list:
every store, the items in the item groups the farm set events to post stock
from, and how much of each is there. Nothing in it can be written back.

Delegates to `common.event_items.stock_overview` so the list and the pickers
can never disagree about what is stock for livestock.
"""

import frappe
from frappe.utils import now_datetime

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.event_items import stock_overview


@frappe.whitelist()
def get_livestock_stock():
	def go():
		guard_read("Herds")
		stores = stock_overview()
		return {
			"ok": True,
			"as_of": str(now_datetime()),
			"stores": stores,
			"count": sum(len(s["items"]) for s in stores),
		}

	return run(go, "livestock mobile get_livestock_stock failed")
