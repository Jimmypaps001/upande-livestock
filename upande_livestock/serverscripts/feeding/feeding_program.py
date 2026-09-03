"""The standing feeding program for a herd.

Read-guarded on Herds."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding import _engine as feeding


@frappe.whitelist()
def feeding_program(herd):
	"""Both sections of the herd feeding programme — the TMR requirement priced
	against the stores, plus a whole-batch plan per concentrate it draws on."""

	def go():
		guard_read("Herds")
		info = feeding.get_herd_feeding_program(herd)
		info["ok"] = True
		return info

	return run(go, "livestock feeding_program failed")
