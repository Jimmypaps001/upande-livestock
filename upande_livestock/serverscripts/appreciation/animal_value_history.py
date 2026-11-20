# Copyright (c) 2026, Upande and contributors
"""Whitelisted door onto common/appreciation. See that module."""

import frappe

from upande_livestock.serverscripts.common import appreciation as core
from upande_livestock.serverscripts.common.envelope import guard_read, run

@frappe.whitelist()
def animal_value_history(animal):
	"""The animal asset's value history: adjustments and depreciation, newest first."""

	def go():
		guard_read("Animal")
		return {"ok": True, **core.value_history(animal)}

	return run(go, "livestock animal_value_history failed")
