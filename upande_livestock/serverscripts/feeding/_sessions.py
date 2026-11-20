# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A herd's feed day mixed in one session (Full) or two (Half-1, Half-2).

Every mix-and-feed, from the System feeding run and from the Day sheet, asks
which it is. Half a day manufactures and issues exactly half of the planned (or
the amended) quantities; the second session is the rest. Each mix is kept as a
Livestock Feed Session row: its share of the day, planned against fed kilograms,
whether the day was amended, and the Stock Entries it moved.

The sessions that are not Cancelled add up to how much of the day the herd has
been fed, and that is the whole state machine:

    nothing fed          -> Not fed
    0 < fed < 1          -> Half fed (1 of 2): a second session is due
    fed >= 1             -> Fully fed

Feeding more than a day (a third session, a Full after a half, the same half
twice) is refused unless a manager overrides it.

A half-fed herd raises a "Feed Session Due" Livestock Alert, delivered at once
through the app's notification channel to the herd's herdsman (users restricted
to the herd, else the Livestock Attendants and Managers), and again as a
reminder at Livestock Settings > Second Session Reminder Time (default 14:00)
when the second session has not happened. Feeding the second session settles it.

This module is not an endpoint: `manufacture_feed` and `manufacture_feed_actuals`
call it.
"""

import json

import frappe
from frappe import _
from frappe.utils import escape_html, flt, get_time, getdate, now_datetime, today

DT = "Livestock Feed Session"
ALERT_KIND = "Feed Session Due"

FRACTION = {"Full": 1.0, "Half-1": 0.5, "Half-2": 0.5}
LABELS = {"Full": "Full day", "Half-1": "Half day, session 1 of 2", "Half-2": "Half day, session 2 of 2"}
STATES = {"not_fed": "Not fed", "half_fed": "Half fed (1 of 2)", "fully_fed": "Fully fed"}
EPS = 1e-6
DEFAULT_REMINDER = "14:00:00"
OVERRIDE_ROLES = ("System Manager", "Livestock Manager")

#: The three Stock Entries a mix links to, and the Work Order.
STOCK_LINKS = ("transfer_stock_entry", "manufacture_stock_entry", "issue_stock_entry")


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------


def normalise(choice):
	"""'Full' | 'Half' | 'Half-1' | 'Half-2' from whatever a screen sent (None is Full)."""
	c = str(choice or "Full").strip().lower().replace("_", "-").replace(" ", "-")
	if c in ("", "full", "full-day", "fullday"):
		return "Full"
	if c in ("half", "half-day", "halfday"):
		return "Half"
	if c in ("half-1", "half-day-1", "half1", "1"):
		return "Half-1"
	if c in ("half-2", "half-day-2", "half2", "2"):
		return "Half-2"
	frappe.throw(_("Choose Full day or Half day."))


def sessions_of(herd, day, include_cancelled=False, for_update=False):
	"""The day's sessions, oldest first, as dicts."""
	filters = {"herd": herd, "date": getdate(day)}
	if not include_cancelled:
		filters["status"] = ["!=", "Cancelled"]
	if for_update:
		# Serialise two taps of Mix on the same herd and day.
		frappe.db.sql(
			"select name from `tabLivestock Feed Session` where herd = %s and date = %s for update",
			(herd, getdate(day)),
		)
	rows = frappe.get_all(
		DT,
		filters=filters,
		fields=[
			"name", "feed_session", "session_fraction", "source", "status", "head_count", "planned_kg",
			"fed_kg", "amended", "operator", "fed_on", "components", "work_order", "overridden",
			"remarks", "creation",
		],
		order_by="creation asc, name asc",
	)
	for r in rows:
		r["components"] = _loads(r.pop("components", None))
		r["label"] = LABELS.get(r["feed_session"], r["feed_session"])
		r["fed_on"] = str(r["fed_on"]) if r.get("fed_on") else None
		r.pop("creation", None)
	return rows


def _loads(text):
	try:
		return json.loads(text) if text else []
	except ValueError:
		return []


def fed_fraction(rows):
	return flt(sum(flt(r["session_fraction"]) for r in rows), 3)


def state_of(fraction):
	if fraction <= EPS:
		return "not_fed"
	return "half_fed" if fraction < 1 - EPS else "fully_fed"


def can_override(user=None):
	return bool(set(frappe.get_roles(user or frappe.session.user)) & set(OVERRIDE_ROLES))


def session_state(herd, day, legacy_fed=False):
	"""The day's feeding state: what has been fed, what is owed, what may be chosen.

	`legacy_fed` marks a day fed before sessions existed (no session rows but a
	mixed record or issues): it counts as one full day.
	"""
	resync(herd, day)
	rows = sessions_of(herd, day)
	fraction = fed_fraction(rows)
	legacy = not rows and bool(legacy_fed)
	if legacy:
		fraction = 1.0
	state = state_of(fraction)
	taken = {r["feed_session"] for r in rows}
	if state == "not_fed":
		choices = ["Full", "Half-1"]
	elif state == "half_fed":
		choices = ["Half-2"] if "Half-2" not in taken else []
	else:
		choices = []
	label = STATES[state]
	if fraction > 1 + EPS:
		label = "Over-fed ({0:g} days)".format(fraction)
	return {
		"state": state,
		"label": label,
		"fed_fraction": fraction,
		"remaining_fraction": flt(max(1.0 - fraction, 0.0), 3),
		"choices": choices,
		"next_session": choices[-1] if state == "half_fed" else None,
		"second_due": state == "half_fed",
		"legacy": legacy,
		"can_override": can_override(),
		"sessions": rows,
	}


# ---------------------------------------------------------------------------
# choosing a session (the state machine and the over-feed guard)
# ---------------------------------------------------------------------------


def resolve(herd, day, choice, override=False):
	"""(feed_session, fraction, overridden) for a mix, or throw.

	'Half' resolves to the next half: session 1 on an unfed day, session 2 after
	a first. A choice that would feed more than a day, or repeat a half, needs a
	manager's override.
	"""
	choice = normalise(choice)
	rows = sessions_of(herd, day, for_update=True)
	fed = fed_fraction(rows)
	taken = {r["feed_session"] for r in rows}
	if choice == "Half":
		choice = "Half-1" if not rows else ("Half-2" if "Half-2" not in taken else "Half-1")
	fraction = FRACTION[choice]
	problem = None
	if fed + fraction > 1 + EPS:
		problem = _("{0} has already been fed {1} on {2}. Feeding {3} would be more than a full day.").format(
			herd, STATES[state_of(fed)].lower() if fed < 1 - EPS else _("a full day"), getdate(day),
			LABELS[choice].lower())
	elif choice in taken:
		problem = _("{0} already had {1} on {2}.").format(herd, LABELS[choice].lower(), getdate(day))
	if not problem:
		return choice, fraction, False
	if not frappe.parse_json(override):
		frappe.throw(problem + " " + _("A manager can override this."))
	if not can_override():
		frappe.throw(problem + " " + _("Only a Livestock Manager or System Manager can override this."))
	return choice, fraction, True


# ---------------------------------------------------------------------------
# recording
# ---------------------------------------------------------------------------


def record(herd, day, feed_session, fraction, source, res, *, heads, components, planned_kg, fed_kg,
           amended=False, employee=None, overridden=False, feed_actual=None, remarks=None):
	"""Keep a finished mix as a session, stamp its documents, and tell the herdsman if due.

	`res` is the engine's answer. `components` is a list of {item_code,
	item_name, uom, planned_kg, fed_kg} for THIS session.
	"""
	doc = frappe.new_doc(DT)
	doc.update(
		{
			"date": getdate(day),
			"herd": herd,
			"feed_session": feed_session,
			"session_fraction": fraction,
			"source": source,
			"status": "Waiting for stock" if res.get("pending") else "Fed",
			"head_count": heads,
			"planned_kg": flt(planned_kg, 3),
			"fed_kg": flt(fed_kg, 3),
			"amended": 1 if amended else 0,
			"operator": employee or res.get("employee"),
			"fed_on": now_datetime(),
			"components": json.dumps(components or []),
			"work_order": res.get("work_order"),
			"transfer_stock_entry": res.get("transfer_stock_entry"),
			"manufacture_stock_entry": res.get("manufacture_stock_entry") or None,
			"issue_stock_entry": res.get("issue_stock_entry") or None,
			"livestock_event": res.get("livestock_event"),
			"feed_actual": feed_actual,
			"overridden": 1 if overridden else 0,
			"remarks": remarks,
		}
	)
	doc.insert(ignore_permissions=True)
	stamp_documents(res, feed_session, fraction)
	res["feed_session"] = feed_session
	res["session_fraction"] = fraction
	res["session_name"] = doc.name
	settle_or_raise(herd, day, feed_session)
	return doc


def stamp_documents(res, feed_session, fraction):
	"""Write the session onto the Work Order and Stock Entries the mix made."""
	values = {"custom_feed_session": feed_session, "custom_session_fraction": fraction}
	targets = [("Work Order", res.get("work_order"))] + [
		("Stock Entry", res.get(k)) for k in STOCK_LINKS
	]
	for doctype, name in targets:
		if not name:
			continue
		meta = frappe.get_meta(doctype)
		present = {k: v for k, v in values.items() if meta.has_field(k)}
		if present:
			frappe.db.set_value(doctype, name, present, update_modified=False)


def plan_components(components, fraction):
	"""Per-session component rows from the day's {planned_kg, actual_kg} rows."""
	return [
		{
			"item_code": c["item_code"],
			"item_name": c.get("item_name") or c["item_code"],
			"uom": c.get("uom") or "",
			"planned_kg": flt(flt(c["planned_kg"]) * fraction, 3),
			"fed_kg": flt(flt(c["actual_kg"]) * fraction, 3),
		}
		for c in components
	]


# ---------------------------------------------------------------------------
# keeping the ledger honest when Stock Entries are cancelled or deleted
# ---------------------------------------------------------------------------


def resync(herd, day):
	"""A session holds only while its Stock Entries stand: all cancelled or deleted -> Cancelled;
	a waiting draft that was posted -> Fed."""
	for r in frappe.get_all(
		DT,
		filters={"herd": herd, "date": getdate(day), "status": ["!=", "Cancelled"]},
		fields=["name", "status", *STOCK_LINKS],
	):
		resync_session(r)


def resync_session(row):
	linked = [row[f] for f in STOCK_LINKS if row.get(f)]
	docstatus = {n: frappe.db.get_value("Stock Entry", n, "docstatus") for n in linked}
	live = [n for n, d in docstatus.items() if d in (0, 1)]
	if linked and not live:
		frappe.db.set_value(DT, row["name"], "status", "Cancelled", update_modified=False)
	elif row["status"] == "Waiting for stock" and docstatus.get(row.get("transfer_stock_entry")) == 1:
		frappe.db.set_value(DT, row["name"], "status", "Fed", update_modified=False)


def unlink_entry(entry_name):
	"""A Stock Entry is being deleted: drop its link from any session (a link would block the delete)."""
	touched = set()
	for f in STOCK_LINKS:
		for name in frappe.get_all(DT, filters={f: entry_name}, pluck="name"):
			frappe.db.set_value(DT, name, f, None, update_modified=False)
			touched.add(name)
	for name in touched:
		row = frappe.db.get_value(DT, name, STOCK_LINKS, as_dict=True)
		live = [
			n for n in (row[f] for f in STOCK_LINKS)
			if n and frappe.db.get_value("Stock Entry", n, "docstatus") in (0, 1)
		]
		if not live:  # the mix is gone: the session is not a feeding any more
			frappe.db.set_value(DT, name, "status", "Cancelled", update_modified=False)


def sessions_for_entry(entry_name):
	return frappe.get_all(
		DT, or_filters=[[f, "=", entry_name] for f in STOCK_LINKS], fields=["herd", "date"]
	)


# ---------------------------------------------------------------------------
# the second-session notification
# ---------------------------------------------------------------------------


def _open_alert(herd, day):
	return frappe.db.get_value(
		"Livestock Alert",
		{"alert_kind": ALERT_KIND, "herd": herd, "alert_date": getdate(day), "status": "Open"},
		"name",
	)


def _herd_label(herd):
	return frappe.db.get_value("Herds", herd, "herd_name") or herd


def settle_or_raise(herd, day, feed_session):
	"""After a mix: a first half raises the alert; reaching a full day settles it."""
	try:
		fraction = fed_fraction(sessions_of(herd, day))
		if state_of(fraction) == "half_fed":
			if getdate(day) == getdate(today()):
				raise_second_due(herd, day)
		else:
			settle_alerts(herd, day, "Fed the second session" if feed_session == "Half-2" else "Fully fed")
	except Exception:
		frappe.log_error(title="livestock feed session: second-session alert failed")


def raise_second_due(herd, day):
	"""Raise (once per herd and day) the Livestock Alert and tell the herdsman now. Returns its name."""
	from upande_livestock.serverscripts.common import notifications

	name = _open_alert(herd, day)
	if name:
		return name
	label = _herd_label(herd)
	doc = frappe.new_doc("Livestock Alert")
	doc.alert_kind = ALERT_KIND
	doc.alert_date = getdate(day)
	doc.herd = herd
	doc.severity = "Due"
	doc.message = _("{0} was fed half a day (session 1 of 2). Feed the second session.").format(escape_html(label))
	doc.detail = frappe.as_json({"date": str(getdate(day)), "session": "Half-1", "reminded": False})
	doc.insert(ignore_permissions=True)
	audience = notifications.audience_for_alert(ALERT_KIND, herd)
	notifications.notify(audience, doc.message, _body(doc), "Livestock Alert", doc.name)
	return doc.name


def _body(alert):
	return "<b>{0}</b> · Herd: {1} · {2}".format(ALERT_KIND, escape_html(alert.herd), alert.alert_date)


def settle_alerts(herd, day, why):
	for name in frappe.get_all(
		"Livestock Alert",
		filters={"alert_kind": ALERT_KIND, "herd": herd, "alert_date": getdate(day), "status": "Open"},
		pluck="name",
	):
		frappe.db.set_value(
			"Livestock Alert",
			name,
			{"status": "Actioned", "actioned_on": now_datetime(), "action_notes": why},
			update_modified=False,
		)


def reminder_time():
	"""Livestock Settings > Second Session Reminder Time as a `datetime.time` (default 14:00)."""
	value = frappe.db.get_single_value("Livestock Settings", "second_session_reminder_time")
	try:
		return get_time(value or DEFAULT_REMINDER)
	except Exception:
		return get_time(DEFAULT_REMINDER)


def reminder_due(now, at, detail):
	"""Is a reminder owed: it is past `at` today and none was sent for this alert."""
	return get_time(now) >= get_time(at) and not (detail or {}).get("reminded")


def send_reminders(now=None):
	"""Scheduler: remind about half-fed herds whose second session has not happened.

	Alerts of earlier days are closed (the day is over). Returns the herds reminded.
	"""
	from upande_livestock.serverscripts.common import notifications

	now = now or now_datetime()
	day = getdate(now)
	reminded = []
	for a in frappe.get_all(
		"Livestock Alert",
		filters={"alert_kind": ALERT_KIND, "status": "Open"},
		fields=["name", "herd", "alert_date", "detail", "message"],
	):
		if getdate(a.alert_date) < day:
			frappe.db.set_value("Livestock Alert", a.name, {
				"status": "Dismissed", "action_notes": "The day ended without a second session."},
				update_modified=False)
			continue
		if state_of(fed_fraction(sessions_of(a.herd, a.alert_date))) != "half_fed":
			settle_alerts(a.herd, a.alert_date, "Fully fed")
			continue
		detail = _loads_dict(a.detail)
		if not reminder_due(now.time(), reminder_time(), detail):
			continue
		label = _herd_label(a.herd)
		subject = _("Reminder: {0} still needs its second feeding session today.").format(escape_html(label))
		notifications.notify(
			notifications.audience_for_alert(ALERT_KIND, a.herd), subject,
			_body(frappe._dict(herd=a.herd, alert_date=a.alert_date)), "Livestock Alert", a.name)
		detail["reminded"] = True
		detail["reminded_at"] = str(now)
		frappe.db.set_value("Livestock Alert", a.name, "detail", frappe.as_json(detail), update_modified=False)
		reminded.append(a.herd)
	return reminded


def _loads_dict(text):
	try:
		out = json.loads(text) if text else {}
		return out if isinstance(out, dict) else {}
	except ValueError:
		return {}


def send_reminders_job():
	"""Scheduler entry point: `send_reminders`, committed."""
	send_reminders()
	frappe.db.commit()
