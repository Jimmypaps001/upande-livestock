# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Days of concentrate cover, for the handset.

What each concentrate is consumed at, what the farm holds, and how long that
lasts. It is on the phone because the person who decides to run the mixer is
standing at the mixer, not at a desk.

NO LONGER A MIXING LIST. Mixing is by the kilo now — a mixer makes a tonne of
meal from a tonne of ingredients whatever the herds are eating — so the batch
counts here are cover arithmetic, not an instruction. See `alerts/_cover`.

Delegates to `alerts._cover.concentrate_plan` rather than recomputing. A mobile
endpoint that worked out its own answer to "how much concentrate do we need"
would be the second implementation this package was reorganised to remove.
"""

import frappe

from upande_livestock.serverscripts.alerts._cover import concentrate_plan
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def get_concentrate_plan(days=7):
	def go():
		# Stated here rather than inherited. It was always enforced — the
		# delegate guards too — but the guard used to sit in a whitelisted
		# endpoint of its own, and now that `concentrate_plan` is a private
		# helper of the cover alert, this file is the endpoint and the check
		# belongs where the endpoint is.
		guard_read("Item")
		return concentrate_plan(days)

	return run(go, "livestock mobile get_concentrate_plan failed")
