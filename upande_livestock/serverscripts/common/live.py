# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Tell open phones that something changed, so they update without a refresh.

ONE LIGHTWEIGHT BROADCAST: `livestock_changed`. It carries identifiers only,
never data: the phone, on hearing it, asks the normal permission-checked
endpoints for what it needs. A message that leaked a milk figure to a user who
may not read it would be a second, unguarded read path; ids cannot.

COALESCED. A husbandry round over 85 animals saves 85 events, and each save
fires a doc event. Each one only *notes* the change into a buffer on
`frappe.local`; the buffer is flushed ONCE, after the transaction commits, as
one message per kind holding every animal name. A rollback drops the buffer, so
a phone is never told about something that did not happen.

AUDIENCE. Frappe 15 rooms: every connected user joins `user:<name>`, only System
Users join `all`, and a phone user is not necessarily one. So the message goes
to the personal room of each enabled user holding a livestock role: the
narrowest room that works for any signed-in livestock user, and one nobody else
can join (the socket's room is fixed by the session the server verified).

NEVER RAISES. A realtime hiccup (redis down, a bad doc) must not fail a save
that was otherwise fine; it is logged and swallowed.
"""

import frappe
from frappe.utils import now

EVENT = "livestock_changed"

#: Past this many names the message says `truncated` and carries none: the phone
#: does a delta sync anyway, and a 3000-name message is not "lightweight".
MAX_NAMES = 300

#: doctype -> kind the phone reacts to.
KINDS = {
	"Animal": "animal",
	"Herds": "animal",
	"Livestock Event": "event",
	"Milk Recording": "event",
	"Livestock Weight Record": "event",
	"Livestock Disposal": "event",
	"Livestock Health Case": "health",
	"Livestock Diagnosis": "health",
	"Livestock Vet": "vet",
	"Livestock Settings": "settings",
	"Stock Entry": "stock",
}

#: Fields naming an animal, per doctype (Animal itself is its own name).
ANIMAL_FIELDS = ("animal", "dam")

_BUFFER = "_livestock_live_buffer"


def _log(title):
	try:
		frappe.log_error(title=title)
	except Exception:
		pass


def _audience():
	from upande_livestock.serverscripts.common.notifications import LIVESTOCK_ROLES, users_for_roles

	return users_for_roles(LIVESTOCK_ROLES)


def note(doc, method=None):
	"""Doc-event handler: remember that `doc` changed; broadcast after commit."""
	try:
		kind = KINDS.get(doc.doctype)
		if not kind:
			return
		if doc.doctype == "Stock Entry" and not _is_livestock_stock_entry(doc):
			return
		buf = getattr(frappe.local, _BUFFER, None)
		if buf is None:
			buf = {}
			setattr(frappe.local, _BUFFER, buf)
			frappe.db.after_commit.add(flush)
			frappe.db.after_rollback.add(clear)
		entry = buf.setdefault(kind, {"doctypes": set(), "names": set(), "animals": set()})
		entry["doctypes"].add(doc.doctype)
		entry["names"].add(doc.name)
		if doc.doctype == "Animal":
			entry["animals"].add(doc.name)
		else:
			for f in ANIMAL_FIELDS:
				v = doc.get(f)
				if v and isinstance(v, str):
					entry["animals"].add(v)
	except Exception:
		_log("livestock_changed: could not note a change")


def clear():
	if hasattr(frappe.local, _BUFFER):
		delattr(frappe.local, _BUFFER)


def flush():
	"""Publish the buffered changes: one message per kind, to each livestock user."""
	buf = getattr(frappe.local, _BUFFER, None)
	clear()
	if not buf:
		return
	try:
		users = _audience()
		if not users:
			return
		modified = now()
		for kind, entry in sorted(buf.items()):
			names, animals = sorted(entry["names"]), sorted(entry["animals"])
			truncated = len(names) > MAX_NAMES or len(animals) > MAX_NAMES
			message = {
				"kind": kind,
				"doctype": sorted(entry["doctypes"])[0],
				"doctypes": sorted(entry["doctypes"]),
				"names": [] if truncated else names,
				"animals": [] if truncated else animals,
				"truncated": truncated,
				"modified": modified,
			}
			for user in users:
				frappe.publish_realtime(EVENT, message, user=user)
	except Exception:
		_log("livestock_changed: could not publish")


def _livestock_stores():
	s = frappe.get_cached_doc("Livestock Settings")
	stores = {r.warehouse for r in (s.get("feed_source_warehouses") or []) if r.warehouse}
	for f in (
		"custom_feed_wip_warehouse",
		"custom_milk_target_warehouse",
		"custom_milk_discard_warehouse",
		"custom_colostrum_warehouse",
	):
		if s.get(f):
			stores.add(s.get(f))
	return stores


def _is_livestock_stock_entry(se):
	"""A Stock Entry of a "Livestock ..." type, a livestock flow's type, or one
	touching a store the livestock settings name."""
	from upande_livestock.serverscripts.common.stock import EVENT_TYPE_PREFIX, livestock_stock_entry_types

	t = se.get("stock_entry_type") or ""
	if t.startswith(EVENT_TYPE_PREFIX) or t in livestock_stock_entry_types():
		return True
	stores = _livestock_stores()
	return any(
		(r.get("s_warehouse") in stores) or (r.get("t_warehouse") in stores) for r in (se.get("items") or [])
	)
