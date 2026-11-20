# Copyright (c) 2026, Upande and contributors
"""Whitelisted door onto common/appreciation. See that module."""

import frappe

from upande_livestock.serverscripts.common import appreciation as core
from upande_livestock.serverscripts.common.envelope import guard_read, run

@frappe.whitelist()
def appraise(animal):
	"""Value from the matrix and the latest weight, with the basis used."""

	def go():
		guard_read("Animal")
		return {"ok": True, **core.appraise(animal)}

	return run(go, "livestock appraise failed")
