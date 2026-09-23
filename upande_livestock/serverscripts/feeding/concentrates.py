# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Every concentrate the farm mixes, with its recipe and what is in store.

Replaces the read half of `concentrate_plan`, which answered a different
question: how many batches to mix to cover N days for the herds that eat it.
A mixer takes a tonne of ingredients and makes a tonne of meal whether there
are forty cows in the shed or none, so there is no head count here and no
calendar. What is left is what a concentrate actually is — a name, a recipe,
what that recipe makes, and how much of it is on the shelf.

Read-guarded on BOM: it discloses what the farm feeds.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding._concentrate import concentrate_list


@frappe.whitelist()
def concentrates():
	def go():
		guard_read("BOM")
		return {"ok": True, "concentrates": concentrate_list()}

	return run(go, "livestock concentrates failed")
