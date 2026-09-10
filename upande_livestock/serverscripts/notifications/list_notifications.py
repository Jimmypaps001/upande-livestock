"""This user's livestock notifications, newest first.

Read-guarded on Notification Log and scoped to the session user — there is no
`for_user` parameter, deliberately, so one user cannot read another's inbox.

Joined to the Livestock Alert each row is anchored to, because that anchor is
where the category, severity and herd live (see common/notifications.py). The
join is also the filter: `category` narrows on the alert's KIND, so paging stays
correct — filtering after the LIMIT would silently return short pages.
"""

import frappe

from upande_livestock.serverscripts.alerts._shared import CATEGORY_OF_KIND, kinds_in_category
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.notifications import ANCHOR, unread_for

#: A page of a list nobody scrolls forever. Above this the page should be
#: filtering, not fetching.
MAX_LIMIT = 200


def _int(value, fallback, low, high):
	try:
		return max(low, min(int(value), high))
	except (TypeError, ValueError):
		return fallback


@frappe.whitelist()
def list_notifications(category=None, unread_only=0, limit=50, offset=0):
	"""A page of notifications, plus the unread count the badge wants anyway."""

	def go():
		guard_read("Notification Log")
		user = frappe.session.user

		params = {
			"user": user,
			"anchor": ANCHOR,
			"limit": _int(limit, 50, 1, MAX_LIMIT),
			"offset": _int(offset, 0, 0, 100000),
		}
		where = ["n.for_user = %(user)s", "n.document_type = %(anchor)s"]
		if str(unread_only) in ("1", "true", "True"):
			where.append("n.`read` = 0")
		if category:
			kinds = kinds_in_category(category)
			if not kinds:
				# An unknown category — a stale bookmark, a renamed tab — is an
				# empty list, not a 500 and not silently "everything".
				return {"ok": True, "notifications": [], "unread": unread_for(user)}
			where.append("a.alert_kind IN %(kinds)s")
			params["kinds"] = kinds

		rows = frappe.db.sql(
			"""
			SELECT n.name, n.subject, n.email_content, n.`read` AS `read`, n.creation,
			       n.document_type, n.document_name,
			       a.alert_kind, a.severity, a.animal, a.herd, a.status AS alert_status
			FROM `tabNotification Log` n
			LEFT JOIN `tabLivestock Alert` a ON a.name = n.document_name
			WHERE {}
			ORDER BY n.creation DESC
			LIMIT %(limit)s OFFSET %(offset)s
			""".format(" AND ".join(where)),
			params,
			as_dict=True,
		)
		for r in rows:
			# Derived, never stored — see alerts/_shared.py for why.
			r["category"] = CATEGORY_OF_KIND.get(r.get("alert_kind"))

		return {"ok": True, "notifications": rows, "unread": unread_for(user)}

	return run(go, "livestock list_notifications failed")
