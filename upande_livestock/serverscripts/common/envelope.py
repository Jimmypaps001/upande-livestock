"""The wrapper every livestock endpoint shares.

Three things every endpoint in this package does identically, kept here so they
cannot drift apart:

* `guard` — the permission check. Asked against the *target* DocType rather than
  a role, so a farm that renames or re-scopes a role does not silently open an
  endpoint.
* `as_dict` — a browser `fetch` sends a JSON string where a desk call sends a
  dict. Every write endpoint has to accept both.
* `run` — the reason this API returns `{"error": ...}` rather than raising. The
  Custom HTML Blocks surface that key verbatim, so a validation message written
  for a farm worker reaches them unchanged instead of becoming a 500. A
  PermissionError is reported the same way but skips the rollback and error log
  a genuine failure needs, since being refused isn't a bug worth a log entry.
"""

import json

import frappe
from frappe import _


def guard(doctype: str, employee: bool = True) -> None:
	"""Raise a clean PermissionError-style throw if the user can't create `doctype`.

	Also refuses a user with no linked Employee (see guards.require_employee):
	every endpoint that records something goes through here, so the phone's
	"view only" rule binds on the server and not only in the UI. Settings and
	configuration endpoints pass `employee=False`.
	"""
	if employee:
		from upande_livestock.serverscripts.common.guards import require_employee

		require_employee(doctype)
	if not frappe.has_permission(doctype, "create"):
		# PermissionError, not the default ValidationError: `run` distinguishes the
		# two, and only the general branch rolls back and writes an Error Log. A
		# refusal is an answer, not a fault — and a phone whose user lacks a role
		# would otherwise fill the log on every screen it opens.
		frappe.throw(_("You are not permitted to create {0}.").format(doctype), frappe.PermissionError)


# Who may book feed and the stock behind it. Stock Entry, Work Order and
# Material Request are ERPNext doctypes and the farm's roles are not ERPNext
# roles: a store keeper should not need Stock Manager (which can edit any stock
# anywhere) to feed a herd. The endpoint checks THESE roles, then does the
# privileged part itself with ignore_permissions. A user who already holds the
# ERPNext permissions keeps working, as before.
STOCK_ROLES = ("Livestock Stores", "Livestock Manager")


def guard_stock(*doctypes: str) -> None:
	"""Raise unless the user is a farm stores/manager role, or holds `doctypes` create.

	Always also requires an Employee (see guards.require_employee).
	"""
	from upande_livestock.serverscripts.common.guards import require_employee

	require_employee()
	roles = set(frappe.get_roles())
	if roles & set(STOCK_ROLES) or "System Manager" in roles:
		return
	if all(frappe.has_permission(dt, "create") for dt in doctypes):
		return
	frappe.throw(
		_("You are not permitted to book stock. This needs the {0} role.").format(
			" or ".join(STOCK_ROLES)
		),
		frappe.PermissionError,
	)


LIVESTOCK_ROLES = (
	"Livestock Manager",
	"Livestock Vet",
	"Livestock Breeder",
	"Livestock Attendant",
	"Livestock Milker",
	"Livestock Stores",
)


# A role for the lab: it files bulk tank figures against milkings and reads
# the quality pages, and nothing else. Kept out of LIVESTOCK_ROLES on purpose —
# that tuple means "may see animals and events", which this role may not.
QUALITY_ROLE = "Livestock Quality"


def livestock_roles(user=None):
	"""The livestock roles `user` (default: the session user) holds, farm roles first.

	Only the app's own roles: a phone needs to know which screens to show, not
	every ERPNext role the person carries.
	"""
	held = set(frappe.get_roles(user or frappe.session.user))
	return [r for r in (*LIVESTOCK_ROLES, QUALITY_ROLE) if r in held]


def guard_read_or_livestock(doctype: str) -> None:
	"""Raise unless the user can read `doctype` or holds any livestock role.

	For a read of an ERPNext doctype (Employee) that the farm roles have no
	DocPerm on and should not be given: the endpoint does the read itself and
	returns only the narrow fields the screen shows.
	"""
	if frappe.has_permission(doctype, "read") or set(frappe.get_roles()) & set(LIVESTOCK_ROLES):
		return
	frappe.throw(_("You are not permitted to read {0}.").format(doctype), frappe.PermissionError)


def guard_read(doctype: str) -> None:
	"""Raise if the user can't read `doctype`.

	The read counterpart to `guard`. Sixteen endpoints — every `*_options` call
	and every dashboard read — had no permission check at all: they answered any
	logged-in user on the site, livestock role or not, because the desk blocks
	were the only caller and the desk had already authenticated. A phone
	authenticating as a real user makes that gap a real one, so the check moves
	to the endpoint where it belongs.

	Kept beside `guard` rather than inlined at each call site so the sixteen
	cannot drift into sixteen slightly different checks.
	"""
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("You are not permitted to read {0}.").format(doctype), frappe.PermissionError)


def guard_write(doctype: str) -> None:
	"""Raise if the user can't change an existing `doctype`.

	The third of the set, and not the same question as `guard`. An endpoint that
	moves a case forward — a vet's verdict, a manager's signature — writes to a
	document somebody else created, and asking whether the user may CREATE a
	Livestock Disposal answers a question nobody asked: a farm that lets every
	herdsman raise a cull case and only a manager amend one is exactly the
	arrangement these two permissions exist to express.
	"""
	if not frappe.has_permission(doctype, "write"):
		frappe.throw(_("You are not permitted to change {0}.").format(doctype), frappe.PermissionError)


def as_dict(value):
	"""Coerce the whitelist arg (JSON string from fetch, or dict) to a dict."""
	if isinstance(value, str):
		try:
			return json.loads(value or "{}")
		except Exception:
			return {}
	return value or {}


def run(fn, log_title: str) -> dict:
	"""Execute `fn`, returning its dict on success or {"error": msg} on failure."""
	try:
		out = fn()
		# Stock issues saved as drafts for want of stock (common/stock): the
		# record stood, and the page must say what is still to post.
		from upande_livestock.serverscripts.common.stock import drafts_made

		from upande_livestock.serverscripts.common.stock import warnings_made

		warnings = warnings_made()
		if warnings and isinstance(out, dict) and not out.get("error"):
			out["stock_warnings"] = warnings
		drafts = drafts_made()
		if drafts and isinstance(out, dict) and not out.get("error"):
			out["stock_drafts"] = drafts
		return out
	except frappe.PermissionError as e:
		out = {"error": str(e) or _("Not permitted.")}
		if type(e).__name__ == "NotEmployee":
			# A stable code, so a client can tell this refusal from a missing
			# role and neither queue the item nor retry it.
			out["code"] = "not_employee"
		return out
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=log_title)
		# Surface the doctype/Server-Script validation message (may be HTML).
		return {"error": str(e) or _("Operation failed.")}
