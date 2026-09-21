"""Naming the batch on a feed transfer, since nobody is there to name it.

Batch tracking is on for 105 Dairy Feed items, 399 Dairy Others and 212 Dairy
Drugs, and a Stock Entry will not submit until every outgoing row of a tracked
item names a batch. Two of the eight feed runs that failed in the week to
2026-09-21 failed on exactly that.

The quieter half of the problem is worse. Feed transfers that did go through
carried a batch 1,394 times, and **every one of them was a `-PREMIGRATION`
batch** — migration opening stock holding trillions of invented units, which is
also why the engine's availability check reads a billion kilos of limestone and
never blocks. Not one feed transfer has ever consumed a real batch.

Spray solved this with a picker: a draft sits on the store page, a storesman
sees what is on offer and chooses. Feeding has no such moment — `_run_manufacture`
creates the transfer and submits it in the same call, because mixed feed is
eaten before anyone would count it. There is nowhere to put a picker without
turning one click into two, so here the rule simply decides, using the same
ordering the storesman is shown: real stock ahead of migration filler, then
first-expiry-first-out, then oldest.

Rows that already name a batch are left exactly as they are, and a row the rule
cannot fill is left blank rather than guessed at — ERPNext's own error naming
the item is more use than a wrong batch that submits.

## Why this imports from upande_scp

The rule and the availability join live there because that is where they were
written and where they are tested, and duplicating either is how two apps come
to disagree about what is in a store. The direction looks odd — feed depending
on spray — but it is safe: `upande_livestock` only ever runs on the Kaitet
bench, which always carries `upande_scp`. It is deliberately not the other way
round, because `upande_scp` also runs on Mona, where neither this app nor
`upande_core` is installed.
"""

import frappe

from upande_scp.serverscripts.store import batch_suggestion
from upande_scp.serverscripts.store.batch_stock import available_in_store


def _tracked_rows(doc) -> list:
	"""Outgoing rows of batch-tracked items that still have no batch.

	Outgoing only: a row with no `s_warehouse` is stock arriving, and ERPNext
	makes the batch for it. One query for the item flags rather than one per
	row — a TMR runs to a dozen ingredients and this is on the path of a feed
	run somebody is waiting on at six in the morning.
	"""
	rows = [
		r
		for r in (doc.get("items") or [])
		if r.get("s_warehouse") and not (r.get("batch_no") or "").strip()
	]
	if not rows:
		return []
	codes = sorted({r.item_code for r in rows if r.item_code})
	if not codes:
		return []
	tracked = {
		name
		for name, flag in frappe.db.sql(
			"SELECT name, has_batch_no FROM `tabItem` WHERE name IN %(codes)s",
			{"codes": codes},
		)
		if flag
	}
	return [r for r in rows if r.item_code in tracked]


def assign_batches(doc) -> int:
	"""Fill in the batches on a draft Stock Entry. Returns how many it set.

	Call before `insert()`. Never raises: a feed run must not be lost because
	the batch helper had a bad day — a row left blank fails afterwards with
	ERPNext's own message, which names the item and is what the operator needs
	anyway.
	"""
	try:
		rows = _tracked_rows(doc)
		if not rows:
			return 0

		available = available_in_store(
			[(r.item_code, r.s_warehouse) for r in rows]
		)
		today = frappe.utils.today()

		filled = 0
		fillers = []
		for r in rows:
			pool = available.get((r.item_code, r.s_warehouse), [])
			plan = batch_suggestion.allocate(r.qty, pool, today)
			if not plan["picks"]:
				# Nothing in that store. Left blank on purpose — see the
				# docstring; a wrong batch that submits is worse than a clear
				# refusal naming the item.
				continue
			chosen = plan["picks"][0]["batch_no"]
			r.batch_no = chosen
			filled += 1
			if batch_suggestion.is_placeholder(chosen):
				fillers.append(f"{r.item_code}={chosen}")

		if fillers:
			# Worth a line in the log: it means the real batches for that feed
			# have run out or were never received, and the run is eating
			# migration stock that does not exist.
			frappe.logger("livestock_batches").warning(
				"feed transfer fell back to migration placeholder batches: "
				+ ", ".join(fillers)
			)
		return filled
	except Exception:
		frappe.logger("livestock_batches").warning(
			"could not assign batches; leaving the rows as they were",
			exc_info=True,
		)
		return 0
