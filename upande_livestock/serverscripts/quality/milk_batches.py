# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""milk_batches: the milked batches a quality test is recorded against.

A batch is one milking session: a date plus a shift (Morning / Afternoon /
Evening, read from the recording's milking time), made up of the submitted
Milk Recordings of every herd milked then. The lab picks a batch first; the test
links to the batch's largest recording (`milk_recording`) and takes the date and
shift from the batch.
"""

import frappe
from frappe.utils import add_days, cint, today

from upande_livestock.serverscripts.common.envelope import guard_read, run

DT = "Milk Quality Test"

SHIFTS = ("Morning", "Afternoon", "Evening")


def shift_of(milking_time) -> str:
	"""The shift a milking time falls in: before noon Morning, before 17:00 Afternoon, else Evening.

	A missing or unreadable time counts as Morning (the first milking of the day)."""
	try:
		hour = int(str(milking_time or "").split(":")[0])
	except ValueError:
		return SHIFTS[0]
	if hour < 12:
		return SHIFTS[0]
	if hour < 17:
		return SHIFTS[1]
	return SHIFTS[2]


def group_batches(rows, tested=None, pending=None) -> list:
	"""Group recording rows into batches, newest first.

	Each row needs name, herd, recording_date, milking_time and net_yield_kg.
	`tested` is the set of recording names that already carry a quality test."""
	tested = set(tested or ())
	pending = set(pending or ())
	batches = {}
	for r in rows:
		date = str(r.get("recording_date"))
		shift = shift_of(r.get("milking_time"))
		b = batches.setdefault(
			(date, shift),
			{"date": date, "shift": shift, "total_kg": 0.0, "herds": [], "recordings": [], "tested": False, "pending": False},
		)
		b["total_kg"] += float(r.get("net_yield_kg") or 0)
		if r.get("herd") and r["herd"] not in b["herds"]:
			b["herds"].append(r["herd"])
		b["recordings"].append({"name": r["name"], "herd": r.get("herd"), "net_yield_kg": float(r.get("net_yield_kg") or 0)})
		if r["name"] in tested:
			b["tested"] = True
		if r["name"] in pending:
			b["pending"] = True  # a recording of it still awaits a lab result
	out = []
	for b in batches.values():
		b["total_kg"] = round(b["total_kg"], 2)
		b["recordings"].sort(key=lambda x: -x["net_yield_kg"])
		b["milk_recording"] = b["recordings"][0]["name"]  # what the test links to
		b["key"] = f"{b['date']}|{b['shift']}"
		out.append(b)
	out.sort(key=lambda b: (b["date"], SHIFTS.index(b["shift"])), reverse=True)
	out.sort(key=lambda b: not b["pending"])  # stable: pending first, newest first within each group
	return out


def batch_recordings(date, shift, include=None) -> list:
	"""Names of the submitted Milk Recordings of one date + shift, plus `include`."""
	rows = frappe.get_all(
		"Milk Recording",
		filters={"docstatus": 1, "recording_date": date},
		fields=["name", "milking_time"],
	)
	names = [r["name"] for r in rows if shift_of(r.get("milking_time")) == shift] if shift else []
	for n in include or ():
		if n and n not in names:
			names.append(n)
	return names


@frappe.whitelist()
def milk_batches(date_from=None, date_to=None):
	"""Milked batches (date + shift) between two dates, default the last 14 days.

	Each: key, date, shift, total_kg, herds, recordings, milk_recording (the one a
	test links to), tested (a quality test already exists against one of them), pending (a recording
	still awaits a lab result; pending batches come first)."""

	def go():
		guard_read(DT)
		frm = date_from or add_days(today(), -14)
		to = date_to or today()
		rows = frappe.get_all(
			"Milk Recording",
			filters={"docstatus": 1, "recording_date": ["between", [frm, to]]},
			fields=["name", "herd", "recording_date", "milking_time", "net_yield_kg", "custom_quality_pending"],
			order_by="recording_date desc, milking_time desc",
			limit=cint(500),
		)
		names = [r["name"] for r in rows]
		tested = (
			{t.milk_recording for t in frappe.get_all(DT, filters={"milk_recording": ["in", names]}, fields=["milk_recording"])}
			if names
			else set()
		)
		pending = {r["name"] for r in rows if r.get("custom_quality_pending")}
		return {"ok": True, "from": str(frm), "to": str(to), "batches": group_batches(rows, tested, pending)}

	return run(go, "livestock milk_batches failed")
