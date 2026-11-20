# Copyright (c) 2026, Upande and contributors
"""Whitelisted door onto common/appreciation. See that module."""

import frappe

from upande_livestock.serverscripts.common import appreciation as core
from upande_livestock.serverscripts.common.envelope import guard_read, run

ROLES = core.POSTING_ROLES


@frappe.whitelist()
def run_appreciation(dry_run=0):
	"""Revalue every live animal's asset. Returns the summary."""

	def go():
		frappe.only_for(ROLES)
		if not core.cint(dry_run) and not core.is_enabled():
			frappe.throw("Appreciation is switched off in Livestock Settings. Run a dry run, or switch it on first.")
		return {"ok": True, **core.run(dry_run=dry_run)}

	return run(go, "livestock run_appreciation failed")
