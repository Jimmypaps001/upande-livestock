# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which herd an animal stood in on a given day.

A Movement event is the only record of a move, so the herd history is rebuilt
from them. The first herd is the one the first Movement left (or, for an animal
that never moved, the herd it is in now). It starts on `acquisition_date` — a
calf's birth date, a bought animal's arrival — or the date of birth.

A span is `(herd, from, to)`: the animal was in `herd` from `from` (the arrival
day counts) up to but not including `to`, the day it left; `to` is None while it
is still there. Two moves on one day: the later one wins.
"""

import datetime

import frappe
from frappe.utils import add_days, getdate

BEGINNING = datetime.date(1900, 1, 1)


def _start(row):
	return getdate(row.acquisition_date or row.date_of_birth) if (row.acquisition_date or row.date_of_birth) else BEGINNING


def _build(row, moves):
	"""Spans for one animal row and its submitted moves, oldest first."""
	if not moves:
		return [(row.current_herd, _start(row), None)] if row.current_herd else []
	spans = []
	first = moves[0]
	if first.current_herd:
		spans.append((first.current_herd, _start(row), getdate(first.event_date)))
	for i, m in enumerate(moves):
		nxt = getdate(moves[i + 1].event_date) if i + 1 < len(moves) else None
		spans.append((m.new_herd, getdate(m.event_date), nxt))
	# A span the next move cancels the same day was never stood in.
	return [s for s in spans if s[2] is None or s[2] > s[1]]


def _moves(animals):
	rows = frappe.get_all(
		"Livestock Event",
		filters={"event_type": "Movement", "docstatus": 1, "animal": ["in", list(animals) or [""]]},
		fields=["animal", "event_date", "current_herd", "new_herd", "creation"],
		order_by="event_date asc, creation asc",
		limit=100000,
	)
	by = {}
	for r in rows:
		by.setdefault(r.animal, []).append(r)
	return by


def _rows(animals):
	return {
		r.name: r
		for r in frappe.get_all(
			"Animal", filters={"name": ["in", list(animals) or [""]]},
			fields=["name", "current_herd", "acquisition_date", "date_of_birth"], limit=100000)
	}


def spans(animal):
	"""[(herd, from, to)] for one animal, oldest first. Empty for an unknown one."""
	rows = _rows([animal])
	if animal not in rows:
		return []
	return _build(rows[animal], _moves([animal]).get(animal, []))


def herd_on(animal, date):
	"""The herd the animal was in on `date`, or None (not yet on the farm)."""
	day = getdate(date)
	found = None
	for herd, start, end in spans(animal):
		if start <= day and (end is None or day < end):
			found = herd
	return found


def _candidates(herd):
	"""Animals that were ever in `herd`: standing in it, or a move touches it."""
	names = set(frappe.get_all("Animal", filters={"current_herd": herd}, pluck="name", limit=100000))
	for field in ("new_herd", "current_herd"):
		names.update(frappe.get_all(
			"Livestock Event",
			filters={"event_type": "Movement", "docstatus": 1, field: herd},
			pluck="animal", limit=100000))
	return names


def spans_in(herd):
	"""{animal: [(from, to)]} — every stay in `herd`."""
	names = _candidates(herd)
	rows, moves = _rows(names), _moves(names)
	out = {}
	for name in names:
		if name not in rows:
			continue
		stays = [(a, b) for h, a, b in _build(rows[name], moves.get(name, [])) if h == herd]
		if stays:
			out[name] = stays
	return out


def members_on(herd, date):
	"""Animal names that were in `herd` on `date` (arrival day included)."""
	day = getdate(date)
	return sorted(
		a for a, stays in spans_in(herd).items()
		if any(s <= day and (e is None or day < e) for s, e in stays))


def present_between(herd, start, end):
	"""{animal: (first_day, last_day)} for animals in `herd` on any day of
	[start, end] (inclusive). The days are clipped to the window."""
	ws, we = getdate(start), getdate(end)
	out = {}
	for animal, stays in spans_in(herd).items():
		days = []
		for s, e in stays:
			last = add_days(e, -1) if e else we
			first_in, last_in = max(s, ws), min(getdate(last), we)
			if first_in <= last_in:
				days.append((first_in, last_in))
		if days:
			out[animal] = (min(d[0] for d in days), max(d[1] for d in days))
	return out
