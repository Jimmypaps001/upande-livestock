# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Feed a herd from the handset: what it would take, then do it.

Two steps the app's feed screen walks in order, behind one frozen path so the
phone does not have to know that manufacturing and issuing are separate
endpoints — or that they moved.

`action` selects the step:

  "info"        what the herd's programme requires and what the store holds
  "day"         how much of today's ration has gone out, and what is owed
  "manufacture" mix the TMR (a Work Order), which also issues it to the herd
  "issue"       issue an already-mixed quantity

`manufacture` takes a `portion`: the farm feeds twice a day, so 0.5 mixes and
issues half the ration and two runs make the day. The phone gets the suggested
portion from "day" rather than assuming a half — a herd already fed once is
owed the remainder, not another half.

The app previously reached `api.feeding` directly — the *unguarded* engine
underneath these endpoints — so a handset could manufacture feed and move stock
with no permission check at all. It went through this package's guarded
endpoints instead; that hole is why the engine is no longer whitelisted.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, run
from upande_livestock.serverscripts.feeding.feed_day_status import feed_day_status
from upande_livestock.serverscripts.feeding.feeding_program import feeding_program
from upande_livestock.serverscripts.feeding.issue_feed import issue_feed
from upande_livestock.serverscripts.feeding.manufacture_feed import manufacture_feed


@frappe.whitelist()
def record_feeding(payload=None):
	def go():
		d = as_dict(payload)
		action = (d.get("action") or "info").strip()
		herd = d.get("herd")
		if not herd:
			frappe.throw(frappe._("Which herd? `herd` is required."))

		if action == "info":
			return feeding_program(herd)
		if action == "day":
			return feed_day_status(herd)
		if action == "manufacture":
			return manufacture_feed(
				herd,
				allow_shortage=d.get("allow_shortage", False),
				employee=d.get("employee"),
				portion=d.get("portion", 1.0),
			)
		if action == "issue":
			return issue_feed(herd, d.get("qty"), employee=d.get("employee"))
		frappe.throw(
			frappe._("{0} is not a feeding action. Known: info, day, manufacture, issue.").format(
				action
			)
		)

	return run(go, "livestock mobile record_feeding failed")
