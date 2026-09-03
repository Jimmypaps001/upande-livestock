"""Which animals are due to move up a growth stage, and which are ready to serve.

Suggests only; it moves nothing. Read-guarded on Herds."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common import herd_movement


@frappe.whitelist()
def movement_suggestions():
	"""What the herd structure says should happen next.

	Read-only. Nothing here moves an animal — it proposes, and a person decides.
	"""

	def go():
		guard_read("Herds")
		from upande_livestock.serverscripts.common import herd_movement

		res = herd_movement.suggestions()
		res["ok"] = True
		return res

	return run(go, "livestock movement_suggestions failed")
