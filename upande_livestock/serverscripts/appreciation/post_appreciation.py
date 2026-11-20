# Copyright (c) 2026, Upande and contributors
"""Whitelisted door onto common/appreciation. See that module."""

import frappe

from upande_livestock.serverscripts.common import appreciation as core
from upande_livestock.serverscripts.common.envelope import guard_read, run

ROLES = core.POSTING_ROLES


@frappe.whitelist()
def post_appreciation(animal, dry_run=1):
	"""Revalue one animal's asset. Dry run (the default) only reports."""

	def go():
		frappe.only_for(ROLES)
		return {"ok": True, **core.post_appreciation(animal, dry_run=dry_run)}

	return run(go, "livestock post_appreciation failed")
