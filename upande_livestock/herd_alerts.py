# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The four things about herd movement somebody should be told.

Each one is CAPTURED here, not delivered. `collect()` answers "what would you
tell someone right now" as plain data, and `raise_alerts()` records each as a
Livestock Alert. How an alert reaches a person — email, the desk, a phone —
is deliberately not decided here, because that decision has not been made yet
and hard-wiring one channel now is what makes it expensive to change later.

  BULL CULL DUE       a bull calf is past the share of its selling window the
                      farm set. On this farm the window is 14 days and the
                      warning fires at 75% of it — day 10.5.
  MOVE DUE            a heifer has served her time on a rung of the growth
                      ladder and the next herd is waiting.
  MOVE OVERDUE        she is past the maximum, not merely due.
  COW OPEN TOO LONG   a cow in the high-yield herd has gone longer than the
                      farm's limit without conceiving, and has expired from
                      that herd on productivity grounds.

An alert is raised once per animal per kind per day. Repeating it hourly is how
people learn to ignore alerts.
"""

import frappe
from frappe.utils import today

from upande_livestock.serverscripts.common import herd_movement

KINDS = ("Bull Cull Due", "Move Due", "Move Overdue", "Cow Open Too Long")


def collect():
	"""Everything worth telling someone, as data. Writes nothing."""
	s = herd_movement.suggestions()
	out = []

	for r in s["bulls"]:
		out.append({
			"kind": "Bull Cull Due",
			"animal": r["animal"],
			"label": r["label"],
			"herd": r["herd"],
			"severity": "Overdue" if r["overdue"] else "Due",
			"message": "{} is {} — {}.".format(
				r["label"],
				"past its selling window" if r["overdue"] else "approaching its selling window",
				r["reason"],
			),
			"detail": {
				"days_on_farm": r["days_on_farm"],
				"window_days": r["window_days"],
				"days_remaining": r["days_remaining"],
			},
		})

	for r in s["growth"]:
		out.append({
			"kind": "Move Overdue" if r["overdue"] else "Move Due",
			"animal": r["animal"],
			"label": r["label"],
			"herd": r["from_herd"],
			"severity": "Overdue" if r["overdue"] else "Due",
			"message": "{} should move from {} to {} — {}.".format(
				r["label"], r["from_herd"], r["to_herd"], r["reason"]
			),
			"detail": {
				"to_herd": r["to_herd"],
				"days_in_herd": r["days_in_herd"],
				"days_expected": r["days_expected"],
				"days_over": r["days_over"],
			},
		})

	for r in s["open_cows"]:
		out.append({
			"kind": "Cow Open Too Long",
			"animal": r["animal"],
			"label": r["label"],
			"herd": r["herd"],
			"severity": "Overdue",
			"message": "{} has not conceived in {} days — {} past the {}-day limit.".format(
				r["label"], r["open_days"], r["days_over"], r["limit"]
			),
			"detail": {"open_days": r["open_days"], "limit": r["limit"], "days_over": r["days_over"]},
		})

	return out


def _already_raised_today(kind, animal):
	return frappe.db.exists("Livestock Alert", {
		"alert_kind": kind,
		"animal": animal,
		"alert_date": today(),
	})


def raise_alerts():
	"""Record today's alerts. Safe to run repeatedly — one per animal per kind
	per day, because an alert repeated hourly is an alert people learn to skip.
	"""
	raised = skipped = 0
	for a in collect():
		if _already_raised_today(a["kind"], a["animal"]):
			skipped += 1
			continue
		doc = frappe.new_doc("Livestock Alert")
		doc.alert_kind = a["kind"]
		doc.alert_date = today()
		doc.animal = a["animal"]
		doc.herd = a["herd"]
		doc.severity = a["severity"]
		doc.message = a["message"]
		doc.detail = frappe.as_json(a["detail"])
		doc.insert(ignore_permissions=True)
		raised += 1
	frappe.db.commit()
	return {"raised": raised, "already_open": skipped}


@frappe.whitelist()
def open_alerts(kind=None, limit=200):
	"""Alerts nobody has actioned yet, newest first."""
	filters = {"status": "Open"}
	if kind:
		filters["alert_kind"] = kind
	rows = frappe.get_all(
		"Livestock Alert",
		filters=filters,
		fields=["name", "alert_kind", "alert_date", "animal", "herd", "severity", "message"],
		order_by="severity asc, alert_date asc",
		limit=int(limit),
	)
	return {
		"ok": True,
		"alerts": rows,
		"counts": {k: sum(1 for r in rows if r.alert_kind == k) for k in KINDS},
	}
