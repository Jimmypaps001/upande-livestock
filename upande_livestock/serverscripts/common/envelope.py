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


def guard(doctype: str) -> None:
	"""Raise a clean PermissionError-style throw if the user can't create `doctype`."""
	if not frappe.has_permission(doctype, "create"):
		# PermissionError, not the default ValidationError: `run` distinguishes the
		# two, and only the general branch rolls back and writes an Error Log. A
		# refusal is an answer, not a fault — and a phone whose user lacks a role
		# would otherwise fill the log on every screen it opens.
		frappe.throw(_("You are not permitted to create {0}.").format(doctype), frappe.PermissionError)


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
		return fn()
	except frappe.PermissionError as e:
		return {"error": str(e) or _("Not permitted.")}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=log_title)
		# Surface the doctype/Server-Script validation message (may be HTML).
		return {"error": str(e) or _("Operation failed.")}
