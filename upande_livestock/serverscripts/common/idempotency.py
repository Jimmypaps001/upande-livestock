# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Make a handset write safe to send twice.

The phone keeps every recording in a queue and sends it when it has signal. A
send whose reply never arrived is sent again, and without help the server files
the thing a second time: two weighings, two services, a herd fed twice.

The phone stamps each recording with a `client_ref` (a uuid it makes once).
`@idempotent` sits between `@frappe.whitelist()` and an endpoint: the first send
runs the endpoint and keeps its answer in the Livestock Client Ref ledger; any
later send of the same ref gets that answer back, marked `duplicate`, and does
nothing. A call with no ref runs as before, so the desk and older phones are
untouched.

The ref may arrive beside the payload (`client_ref=...`) or inside it
(`payload.client_ref`). Calls are serialised per ref with a database lock and
the ledger row is committed before the lock goes, so two copies of one send
racing each other cannot both run. A refusal (`{"error": ...}`) is not kept: the
person fixes it and sends again under the same ref.
"""

import functools
import json

import frappe

from upande_livestock.serverscripts.common.envelope import as_dict

DT = "Livestock Client Ref"
LOCK_SECONDS = 30


def client_ref_of(kwargs=None) -> str:
	"""The ref of the current request, from the form or from its payload."""
	form = frappe.local.form_dict or {}
	ref = form.get("client_ref")
	if not ref:
		for source in (form.get("payload"), (kwargs or {}).get("payload")):
			if source:
				ref = as_dict(source).get("client_ref")
				if ref:
					break
	return str(ref).strip()[:140] if ref else ""


def _lock_name(ref: str) -> str:
	# MariaDB lock names are capped at 64 characters.
	import hashlib

	return "lsck_" + hashlib.sha1(ref.encode()).hexdigest()[:40]


def remembered(ref: str):
	"""The answer kept for `ref`, or None. A locking read, so it sees rows another
	request committed after this one's snapshot began."""
	rows = frappe.db.sql(
		f"select result from `tab{DT}` where name = %s for update", (ref,)
	)
	if not rows:
		return None
	try:
		out = json.loads(rows[0][0] or "{}")
	except Exception:
		out = {}
	if isinstance(out, dict):
		out["duplicate"] = True
	return out


def remember(ref: str, endpoint: str, result) -> None:
	doc = frappe.get_doc(
		{
			"doctype": DT,
			"client_ref": ref,
			"endpoint": endpoint[:140],
			"user": frappe.session.user,
			"result": json.dumps(result, default=str),
		}
	)
	doc.insert(ignore_permissions=True)


def idempotent(fn):
	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		ref = client_ref_of(kwargs)
		if not ref:
			return fn(*args, **kwargs)

		lock = _lock_name(ref)
		got = frappe.db.sql("select get_lock(%s, %s)", (lock, LOCK_SECONDS))[0][0]
		if not got:
			return {"error": frappe._("This recording is already being filed. Try again in a moment."), "retry": True}
		try:
			# Start from a fresh snapshot so a row committed while we waited is seen.
			frappe.db.commit()
			prior = remembered(ref)
			if prior is not None:
				return prior
			result = fn(*args, **kwargs)
			if isinstance(result, dict) and not result.get("error"):
				remember(ref, f"{fn.__module__}.{fn.__name__}", result)
				frappe.db.commit()
			return result
		finally:
			frappe.db.sql("select release_lock(%s)", (lock,))

	return wrapper
