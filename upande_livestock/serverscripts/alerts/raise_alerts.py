"""The nightly alert sweep: what should be said about herd movement.

Records alerts; it does not deliver them — that channel is still to be decided.
Not an endpoint: hooks.py runs it on the daily scheduler, so it has no caller
to guard against.
"""

import frappe
from frappe.utils import today

from upande_livestock.serverscripts.alerts._shared import KINDS
from upande_livestock.serverscripts.common import herd_movement




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
