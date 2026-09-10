# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The delivery channel for livestock alerts.

hooks.py's daily sweep used to say the channel "is still to be decided". It is
Frappe's ``Notification Log`` — the doctype holding notification *instances*,
which is what the desk bell reads and what this app's Notifications page reads
back.

(``Notification`` is a DIFFERENT doctype: alert *rules*. We deliberately do not
use it. A Livestock Alert is raised by a nightly Python sweep over herd
structure and breeding dates — not by a condition evaluated on a document save,
which is the only thing ``Notification`` can express.)

EVERY LIVESTOCK NOTIFICATION IS ANCHORED TO THE ALERT THAT EARNED IT, through
``document_type``/``document_name``. That one decision buys three things:

  * *Idempotency.* The scheduler re-sees the same open alert every night.
    Delivery skips any (alert, user) pair that already has a row, so a second
    run sends nothing. No "delivered" flag on Livestock Alert — that would be a
    second source of truth to keep in step with the rows themselves, and it
    could not express "delivered to Alice but not yet to Bob, who joined today".
  * *Scope.* This site also runs upande_scp, which writes its own Notification
    Log rows. Counting only rows anchored to a Livestock Alert is what stops a
    chemical transfer from inflating the livestock unread badge.
  * *Category.* The taxonomy is read from the anchor's ``alert_kind`` (see
    alerts/_shared.py) at query time rather than copied onto a column of its
    own, so a kind cannot end up filed under two categories at once.

The cost of the anchor is stated plainly: a livestock notification that is NOT
about a Livestock Alert would be invisible to these endpoints. Nothing raises
one today, and anything that wants to should raise the alert first — the alert
row is what the farm actions, dismisses and reports on.

Audience is resolved HERE, from livestock roles and from any herd restriction —
never passed in by a client. Notifying is best-effort: a notification that fails
must never roll back the sweep that earned it.
"""

import frappe
from frappe.utils import escape_html, formatdate

from upande_livestock.serverscripts.alerts._shared import KINDS

#: Realtime event the desk subscribes to. The SPA at /livestock_app is served by
#: a plain www page that never loads Frappe's socketio bundle, so it polls
#: instead (frontend/src/hooks/use-notifications.ts) — this is for the desk.
EVENT = "livestock:notification"

#: The doctype every livestock notification points at. See the module docstring.
ANCHOR = "Livestock Alert"

#: The six livestock roles on this site. Named once, so "everyone responsible
#: for livestock" has one definition rather than six half-remembered ones.
LIVESTOCK_ROLES = (
	"Livestock Manager",
	"Livestock Vet",
	"Livestock Breeder",
	"Livestock Attendant",
	"Livestock Stores",
	"Livestock Milker",
)

#: Who hears about what. Deliberately narrower than LIVESTOCK_ROLES: a milker
#: has no say in whether a bull is past its selling window, and a store keeper
#: does not decide when a cow is served. Notifying all six would be the fastest
#: way to teach the farm to ignore the bell.
ROLES_FOR_KIND = {
	# Where an animal belongs. The attendant walks it; the manager approves it.
	"Bull Cull Due": ("Livestock Manager", "Livestock Attendant"),
	"Move Due": ("Livestock Manager", "Livestock Attendant"),
	"Move Overdue": ("Livestock Manager", "Livestock Attendant"),
	# The breeding calendar. The breeder acts, the vet is who a stalled cow
	# ends up in front of.
	"Cow Open Too Long": ("Livestock Manager", "Livestock Breeder", "Livestock Vet"),
	"Pregnancy Check Overdue": ("Livestock Manager", "Livestock Breeder", "Livestock Vet"),
	# A calving needs a pen prepared and the cow watched, which is attendant
	# work, as well as the breeder who has been tracking the pregnancy.
	"Calving Due": ("Livestock Manager", "Livestock Breeder", "Livestock Attendant"),
}

#: A kind nobody thought to map still reaches the person accountable for the
#: herd, rather than silently reaching nobody.
DEFAULT_ROLES = ("Livestock Manager",)

_NEVER_NOTIFY = {"Administrator", "Guest", "", None}


# ---------------------------------------------------------------------------
# audience
# ---------------------------------------------------------------------------


def _clean(users):
	"""De-duplicate, drop system accounts, keep only enabled users."""
	wanted = {u for u in (users or []) if u not in _NEVER_NOTIFY}
	if not wanted:
		return []
	enabled = frappe.get_all(
		"User",
		filters={"name": ("in", list(wanted)), "enabled": 1},
		pluck="name",
	)
	return sorted(enabled)


def users_for_role(role):
	"""Enabled users holding `role`."""
	if not role:
		return []
	return _clean(
		frappe.get_all(
			"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"
		)
	)


def users_for_roles(roles):
	"""Enabled users holding any of `roles`."""
	found = []
	for role in roles or ():
		found += users_for_role(role)
	return _clean(found)


def users_for_herd(herd):
	"""Users restricted to this herd by a User Permission.

	The sibling app asks who is actually assigned to a store before falling back
	to a whole role; a herd is this app's equivalent of that assignment. Herds
	carries no owner field, so the assignment that exists is Frappe's own:
	a `User Permission` on Herds.

	No user is restricted to a herd on kaitet today, so in practice this returns
	nothing and `audience_for_alert` falls back to the role audience — which is
	the point. The day somebody IS restricted to Steamers, Steamers' alerts stop
	going to the people who cannot see that herd anyway.
	"""
	if not herd:
		return []
	return _clean(
		frappe.get_all(
			"User Permission",
			filters={"allow": "Herds", "for_value": herd},
			pluck="user",
		)
	)


def _herd_restricted_users():
	"""Everyone who has ANY Herds restriction.

	Needed because Frappe's rule is the absence of a permission, not its
	presence: a user with no User Permission on Herds is responsible for every
	herd, and only a user who has one is narrowed to the herds it names.
	"""
	return set(frappe.get_all("User Permission", filters={"allow": "Herds"}, pluck="user"))


def audience_for_alert(kind, herd=None):
	"""Who should hear about an alert of `kind` about `herd`.

	Roles decide the job; the herd restriction, if anyone has one, decides the
	patch. Someone with no restriction stays in — see `_herd_restricted_users`.
	"""
	by_role = set(users_for_roles(ROLES_FOR_KIND.get(kind, DEFAULT_ROLES)))
	if not by_role or not herd:
		return sorted(by_role)
	restricted = _herd_restricted_users()
	if not restricted:
		return sorted(by_role)
	allowed = set(users_for_herd(herd))
	return sorted(u for u in by_role if u not in restricted or u in allowed)


# ---------------------------------------------------------------------------
# sending
# ---------------------------------------------------------------------------


def notify(users, subject, body="", ref_doctype=None, ref_name=None):
	"""Write one Notification Log row per user. Returns the users notified.

	Best-effort by design: a failure here is logged and swallowed, because the
	work that earned the notification — a night's alert sweep — must not be
	undone by a notification problem.

	`subject` and `body` are stored as written and rendered as HTML by both the
	desk bell and this app's page, so callers escape anything that came out of
	the database. `_subject`/`_body` below do exactly that.
	"""
	recipients = _clean(users if isinstance(users, list | tuple | set) else [users])
	if not recipients:
		return []

	sent = []
	for user in recipients:
		try:
			frappe.get_doc({
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"email_content": body or subject,
				"document_type": ref_doctype,
				"document_name": ref_name,
			}).insert(ignore_permissions=True)
			sent.append(user)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "livestock notify insert failed")

	for user in sent:
		try:
			frappe.publish_realtime(EVENT, {"document_type": ref_doctype}, user=user)
		except Exception:
			# Realtime is an optimisation; the row is already stored and every
			# reader recomputes its count on load.
			pass
	return sent


def _subject(alert):
	"""The alert's own sentence. It already names the animal and says why."""
	return escape_html(alert.get("message") or alert.get("alert_kind") or "Livestock alert")


def _body(alert):
	"""The facts behind the sentence, so a reader can act without opening it."""
	bits = ["<b>{}</b>".format(escape_html(alert.get("alert_kind") or ""))]
	for label, value in (
		("Severity", alert.get("severity")),
		("Herd", alert.get("herd")),
		("Animal", alert.get("animal")),
	):
		if value:
			bits.append(f"{label}: {escape_html(str(value))}")
	if alert.get("alert_date"):
		bits.append("Raised " + escape_html(formatdate(alert.get("alert_date"))))
	return " · ".join(bits)


def deliver_open_alerts(limit=1000):
	"""Deliver every still-open Livestock Alert to the people responsible, once.

	Does NOT commit. The scheduled callers commit around it, which is what makes
	the skip durable across a crash mid-sweep; leaving the commit to them also
	keeps a test's transaction its own.

	Only OPEN alerts are delivered — an alert somebody has already actioned or
	dismissed is not news. That also bounds what a newly-hired vet receives on
	their first night to the work that is genuinely outstanding, which is the
	right answer rather than a side effect.
	"""
	alerts = frappe.get_all(
		ANCHOR,
		filters={"status": "Open", "alert_kind": ("in", KINDS)},
		fields=["name", "alert_kind", "severity", "alert_date", "animal", "herd", "message"],
		order_by="alert_date asc",
		limit_page_length=int(limit),
	)
	if not alerts:
		return {"alerts": 0, "delivered": 0, "skipped": 0}

	# One query for the whole run rather than an exists() per (alert, user):
	# a nightly sweep over an open backlog would otherwise be hundreds of them.
	already = {
		(r.document_name, r.for_user)
		for r in frappe.get_all(
			"Notification Log",
			filters={"document_type": ANCHOR, "document_name": ("in", [a.name for a in alerts])},
			fields=["document_name", "for_user"],
			limit_page_length=0,
		)
	}

	delivered = skipped = 0
	for alert in alerts:
		audience = audience_for_alert(alert.alert_kind, alert.herd)
		targets = [u for u in audience if (alert.name, u) not in already]
		skipped += len(audience) - len(targets)
		if not targets:
			continue
		delivered += len(notify(targets, _subject(alert), _body(alert), ANCHOR, alert.name))
	return {"alerts": len(alerts), "delivered": delivered, "skipped": skipped}


# ---------------------------------------------------------------------------
# reading — shared by the endpoints, which each own one call
# ---------------------------------------------------------------------------


def unread_for(user):
	"""How many livestock notifications `user` has not read.

	Anchored, so an upande_scp notification on the same site never shows up in
	this app's badge.
	"""
	return frappe.db.count(
		"Notification Log", {"for_user": user, "read": 0, "document_type": ANCHOR}
	)
