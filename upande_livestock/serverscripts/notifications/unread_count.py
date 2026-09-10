"""How many livestock notifications this user has not read.

Read-guarded on Notification Log, and scoped to the session user — there is no
`for_user` parameter, deliberately, so one user cannot count another's.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.notifications import unread_for


@frappe.whitelist()
def unread_count():
	"""The badge number. Counts only rows anchored to a Livestock Alert.

	Returns an envelope rather than a bare integer: lib/frappe.ts hands back the
	`message` only when it is an object, so a naked count would reach the page
	as "No response from the server."
	"""

	def go():
		guard_read("Notification Log")
		return {"ok": True, "unread": unread_for(frappe.session.user)}

	return run(go, "livestock unread_count failed")
