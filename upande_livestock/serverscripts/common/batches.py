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
from frappe import _
from frappe.utils import flt

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


def _tracked_items(codes):
	"""Which of `codes` are batch tracked. The rest are never asked for a batch.

	`_tracked_rows` already filters on this before anything is assigned, so a
	line the store cannot batch is simply not the splitter's business — and the
	picker must know it too, or every un-batched silage line reads "the run
	will refuse" on a page where most lines are un-batched.
	"""
	codes = sorted({c for c in codes if c})
	if not codes:
		return set()
	return {
		name
		for name, flag in frappe.db.sql(
			"SELECT name, has_batch_no FROM `tabItem` WHERE name IN %(codes)s", {"codes": codes}
		)
		if flag
	}


def _held_on_disabled_batches(pairs: list) -> dict:
	"""`{(item_code, warehouse): [{batch_no, qty}]}` for stock nobody can take.

	The mirror of `available_in_store`, which says `AND bt.disabled = 0` and is
	right to: ERPNext refuses to consume a disabled batch. But that makes a
	store holding 48 kg offer nothing, and the page had no way to say why — it
	showed "48 available" beside an empty Batch cell, and the run then refused
	with a shortfall the operator could not account for.

	On live that is not an edge case. All 1,971 `-PREMIGRATION` batches are
	disabled, and seven of the twenty stocked feed lines hold every kilo they
	have on one: `Dry Cows  Meal` keeps its whole 48 kg on
	`Dry Cows  Meal-PREMIGRATION`. Naming the batch turns a blank into a job.

	Asked only for the pairs that came up empty, so a normal run never pays for
	it. Never raises: this is an explanation, and failing to explain must not
	cost the farm its answer.
	"""
	if not pairs:
		return {}
	items = sorted({p[0] for p in pairs})
	houses = sorted({p[1] for p in pairs if p[1]})
	if not items or not houses:
		return {}

	try:
		rows = frappe.db.sql(
			"""
			SELECT sle.item_code, sbe.warehouse, sbe.batch_no, SUM(sbe.qty) AS qty
			FROM   `tabStock Ledger Entry` sle
			JOIN   `tabSerial and Batch Entry` sbe
			       ON sbe.parent = sle.serial_and_batch_bundle
			JOIN   `tabBatch` bt ON bt.name = sbe.batch_no
			WHERE  sle.is_cancelled = 0
			  AND  bt.disabled = 1
			  AND  sle.item_code IN %(items)s
			  AND  sbe.warehouse IN %(houses)s
			GROUP  BY sle.item_code, sbe.warehouse, sbe.batch_no
			HAVING SUM(sbe.qty) > 0
			""",
			{"items": items, "houses": houses},
			as_dict=True,
		)
	except Exception:
		frappe.logger("livestock_batches").warning(
			"could not look up disabled-batch holdings", exc_info=True
		)
		return {}

	out: dict = {}
	for r in rows:
		out.setdefault((r["item_code"], r["warehouse"]), []).append(
			{"batch_no": r["batch_no"], "qty": flt(r["qty"])}
		)
	return out


def _plan_for(rows):
	"""``[(row, picks, short)]`` — what each row would be split into."""
	available = available_in_store([(r.item_code, r.s_warehouse) for r in rows])
	today = frappe.utils.today()
	out = []
	for r in rows:
		pool = available.get((r.item_code, r.s_warehouse), [])
		plan = batch_suggestion.allocate(r.qty, pool, today)
		out.append((r, plan["picks"], flt(plan.get("short"))))
	return out


def suggest_batches(lines):
	"""What the picker shows before anything is posted.

	`lines` is ``[{item_code, qty, warehouse}]``. Each answer carries the
	proposal (`picks`, first-expiry-first-out), everything else the store holds
	(`available`, so the operator can choose differently), and what the store
	cannot cover (`short`).

	Read-only. Nothing here writes, so a page may call it as often as the
	operator changes a store or a quantity.
	"""
	rows = [
		frappe._dict(
			item_code=ln.get("item_code"),
			qty=flt(ln.get("qty")),
			s_warehouse=ln.get("warehouse"),
		)
		for ln in lines or []
		if ln.get("item_code") and ln.get("warehouse")
	]
	if not rows:
		return []

	tracked = _tracked_items([r.item_code for r in rows])
	available = available_in_store([(r.item_code, r.s_warehouse) for r in rows])
	# Only the pairs that came up empty, and only the tracked ones. A store
	# that can answer needs no explanation, and an untracked item is never
	# asked for a batch in the first place.
	held = _held_on_disabled_batches(
		[
			(r.item_code, r.s_warehouse)
			for r in rows
			if r.item_code in tracked and not available.get((r.item_code, r.s_warehouse))
		]
	)
	today = frappe.utils.today()
	out = []
	for r in rows:
		pool = available.get((r.item_code, r.s_warehouse), [])
		plan = batch_suggestion.allocate(r.qty, pool, today)
		is_tracked = r.item_code in tracked
		out.append(
			{
				"item_code": r.item_code,
				"warehouse": r.s_warehouse,
				"required_qty": r.qty,
				# An untracked item is never asked for a batch, so it can never
				# be short of one. Reporting a shortfall it cannot have is how a
				# page ends up warning about every line on it.
				"tracked": is_tracked,
				"picks": [{"batch_no": p["batch_no"], "qty": flt(p["qty"])} for p in plan["picks"]]
				if is_tracked
				else [],
				"short": flt(plan.get("short")) if is_tracked else 0.0,
				# Stock that is here and cannot be taken, because the batch
				# holding it is disabled. The difference between "this store is
				# empty" and "this store is full of stock nobody can issue" is
				# the whole of what the operator needs to know.
				"blocked_by": held.get((r.item_code, r.s_warehouse), []) if is_tracked else [],
				"available": [
					{
						"batch_no": b.get("batch_no"),
						"qty": flt(b.get("qty")),
						"expiry_date": b.get("expiry_date"),
					}
					for b in pool
				],
			}
		)
	return out


def assign_batches(doc) -> int:
	"""Fill in the batches on a draft Stock Entry. Returns how many rows it set.

	Call before `insert()`.

	A ROW IS SPLIT ACROSS THE BATCHES THAT COVER IT. `allocate` says so in its
	own docstring — one Stock Entry row carries one `batch_no`, so a line
	needing more than one batch becomes more than one row. Taking only the
	first pick and leaving the whole quantity on it is how a batch holding
	10,000 is asked for 20,000, and how batch DAIR-2026-00037 reached net
	-32,381 in the concentrate store.

	A LINE THE SOUND BATCHES CANNOT COVER REFUSES. This used to leave the row
	blank, reasoning that ERPNext's own error naming the item was more use than
	a guess. That is true of the error and false of the behaviour: with
	`auto_create_serial_and_batch_bundle_for_outward` on, ERPNext does not
	error on a blank row, it PICKS — by a FIFO happy to choose a batch the
	ledger does not back. Refusing here names the item, the store and the
	shortfall, and stops the run. It is meant to stop runs that used to limp
	through.

	Everything else is still swallowed: a feed run must not be lost because
	this helper had a bad day. The refusal is raised deliberately and is let
	through.
	"""
	try:
		rows = _tracked_rows(doc)
		if not rows:
			return 0
		plan = _plan_for(rows)
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.logger("livestock_batches").warning(
			"could not assign batches; leaving the rows as they were", exc_info=True
		)
		return 0

	failing = [(r, gap) for r, picks, gap in plan if gap > 0 or not picks]
	if failing:
		# Why, not just how much. A run posted from the mobile round never
		# passes the picker, so this sentence is the only one that operator
		# reads — and "48 short" beside a store holding exactly 48 is what sent
		# somebody looking for stock that was already in front of them. The
		# stock is there; the batch holding it is disabled, and ERPNext will
		# not issue from a disabled batch.
		held = _held_on_disabled_batches([(r.item_code, r.s_warehouse) for r, _gap in failing])
		short = []
		for r, gap in failing:
			line = "{0}: {1:g} short in {2}".format(r.item_code, gap, r.s_warehouse)
			blocked = held.get((r.item_code, r.s_warehouse)) or []
			if blocked:
				worst = max(blocked, key=lambda b: b["qty"])
				line += _(" ({0:g} there is on disabled batch {1})").format(
					worst["qty"], worst["batch_no"]
				)
			short.append(line)
		frappe.throw(
			_("No batch in the store can cover this run: {0}.").format("; ".join(short)),
			title=_("Not enough batched stock"),
		)

	try:
		filled = _apply(doc, plan)
	except Exception:
		frappe.logger("livestock_batches").warning(
			"could not apply the batch plan; leaving the rows as they were", exc_info=True
		)
		return 0
	return filled


def _apply(doc, plan):
	"""Rewrite `doc.items`, splitting each planned row across its batches."""
	by_row = {id(r): picks for r, picks, _short in plan}
	rebuilt = []
	filled = 0
	fillers = []

	for row in doc.get("items") or []:
		picks = by_row.get(id(row))
		if not picks:
			rebuilt.append(row)
			continue
		for n, pick in enumerate(picks):
			# The first pick keeps the original row so anything the caller set
			# on it — cost centre, expense account, the employee grid — stays
			# put. The rest are copies of it with their own batch and quantity.
			target = row if n == 0 else _copy_row(doc, row)
			target.qty = flt(pick["qty"])
			target.batch_no = pick["batch_no"]
			# See upande_scp 32dd07b: naming the batch is not enough with
			# auto-bundle on, or ERPNext replaces the pick or refuses the submit.
			target.use_serial_batch_fields = 1
			rebuilt.append(target)
			filled += 1
			if batch_suggestion.is_placeholder(pick["batch_no"]):
				fillers.append(f"{row.item_code}={pick['batch_no']}")

	doc.set("items", rebuilt)
	for n, row in enumerate(rebuilt, start=1):
		if hasattr(row, "idx") or isinstance(row, dict):
			row.idx = n

	if fillers:
		# The real batches for that feed have run out or were never received,
		# and the run is eating migration stock that does not exist.
		frappe.logger("livestock_batches").warning(
			"feed transfer fell back to migration placeholder batches: " + ", ".join(fillers)
		)
	return filled


def _copy_row(doc, row):
	"""Another Stock Entry row exactly like `row`, for a second batch."""
	try:
		copy = doc.append("items", {})
		for field, value in (row.as_dict() if hasattr(row, "as_dict") else dict(row)).items():
			if field in ("name", "idx", "creation", "modified"):
				continue
			setattr(copy, field, value)
		# `append` already put it on the doc; `_apply` rebuilds the list itself.
		if doc.get("items") and doc.get("items")[-1] is copy:
			doc.get("items").pop()
		return copy
	except Exception:
		# A plain dict row in a test, or a doc that cannot append: a shallow
		# copy carries every field the splitter needs.
		return type(row)(dict(row)) if isinstance(row, dict) else row
