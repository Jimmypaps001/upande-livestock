"""Manager tool: turn the typed bulls into Livestock Sire records and link them.

`match_sires(dry_run=1)` returns the proposal and writes nothing; `dry_run=0`
creates the sires and links the Services, Calvings and calves that carry the
text. The text itself is left alone.
"""

import frappe

from upande_livestock.serverscripts.common import livestock_sire as LS
from upande_livestock.serverscripts.common.envelope import run


@frappe.whitelist()
def match_sires(dry_run=1):
	def go():
		frappe.only_for(("Livestock Manager", "System Manager"))
		dry = str(dry_run).lower() not in ("0", "false", "no", "")
		result = LS.match_all(dry_run=dry)
		return {"ok": True, **result}

	return run(go, "livestock match_sires failed")
