# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The week's mixing list, for the handset.

The same plan the desk shows: what each concentrate is consumed at, what the
farm holds, and how many whole batches close the gap. It is on the phone because
the person who decides to run the mixer is standing at the mixer, not at a desk.

Delegates to `feeding.concentrate_plan` rather than recomputing. A mobile
endpoint that worked out its own answer to "how much concentrate do we need"
would be the second implementation this package was reorganised to remove.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import run
from upande_livestock.serverscripts.feeding.concentrate_plan import concentrate_plan


@frappe.whitelist()
def get_concentrate_plan(days=7):
	def go():
		return concentrate_plan(days)

	return run(go, "livestock mobile get_concentrate_plan failed")
