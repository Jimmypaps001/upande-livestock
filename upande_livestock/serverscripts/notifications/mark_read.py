"""Mark this user's livestock notifications as read.

Read-guarded on Notification Log rather than write-guarded, and the reason is
worth saying: every statement here is scoped by `for_user = session.user`, so
the only rows reachable are the ones the caller may already read. `guard`'s
write check asks whether the user may CREATE a Notification Log, which is a
different and irrelevant question — a farm worker who may read their bell must
be able to clear it.

There is no explicit commit. Frappe commits a successful whitelisted POST, and
`run` rolls back a failed one; committing here as well would only take the write
outside the caller's transaction — which, in a test, is the caller's isolation.
"""

import json

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.notifications import ANCHOR, unread_for


def _names(value):
	"""Coerce the whitelist arg (a JSON array from fetch, a list, or one name)."""
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
		except (TypeError, ValueError):
			return [value]
		return parsed if isinstance(parsed, list) else [parsed]
	if isinstance(value, list | tuple):
		return list(value)
	return [value] if value else []


@frappe.whitelist()
def mark_read(names=None, all=0):
	"""Mark the named notifications, or every livestock one, as read."""

	def go():
		guard_read("Notification Log")
		user = frappe.session.user

		if str(all) in ("1", "true", "True"):
			# Anchored, so "mark all read" here never silently clears an
			# upande_scp notification the same user is still waiting on.
			frappe.db.set_value(
				"Notification Log",
				{"for_user": user, "read": 0, "document_type": ANCHOR},
				"read",
				1,
				update_modified=False,
			)
			return {"ok": True, "unread": 0}

		for name in _names(names):
			# Scoped by for_user as well as name, so a guessed name from
			# another user's inbox cannot be touched.
			frappe.db.set_value(
				"Notification Log",
				{"name": name, "for_user": user, "document_type": ANCHOR},
				"read",
				1,
				update_modified=False,
			)
		return {"ok": True, "unread": unread_for(user)}

	return run(go, "livestock mark_read failed")
