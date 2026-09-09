"""Can this feed run post on that day, and if not, when could it?

`_engine.resolve_requirement` prices a run against `Bin`, which holds today's
balance and nothing else. A backdated run has to be judged against the ledger as
it stood on the day, which is what `get_stock_balance` answers.

Relying on ERPNext's own NegativeStockError instead was tried and is not good
enough for this screen: it names the first item it trips over, gives no date, and
by the time it fires a Work Order and a transfer have already been written and
have to be rolled back. This runs first and writes nothing.

`resolve_requirement` reloads the BOM document and walks the candidate
warehouses — none of that varies by day, only the ledger balance does. So every
function below resolves the requirement AT MOST ONCE and then reuses the
resolved lines for however many days it needs to price; only `_short_lines_on`
runs per day, and all it does per day is `get_stock_balance`.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

from erpnext.stock.utils import get_stock_balance

from upande_livestock.serverscripts.feeding._engine import resolve_requirement

# How far back to look for a workable day before giving up. A farm loading a
# season of history does not benefit from being told about a date eight months
# ago that it cannot use either.
SEARCH_DAYS = 90


def _short_lines_on(lines, posting_date, posting_time=None):
	"""Shortfall rows for already-resolved `lines` on `posting_date`.

	The only day-dependent work is the `get_stock_balance` read per line —
	`lines` itself (required qty, source warehouse, item, uom) does not change
	from one day to the next, so callers resolve it once and pass it in here
	however many times they need to price a day.

	`posting_time` matters as much as the date for a day that already has an
	earlier run on it: two backdated runs for the same herd on the same date
	both used to price at the same implicit instant, so the second never saw
	the first's consumption and passed a check it should have failed — the
	gap only showed up at ERPNext's own submit, after a Work Order and a
	transfer already existed. Passing the exact time the run is about to post
	at (see `_engine._run_posting_time`) makes this read exactly what that
	posting will see. Left `None` (get_stock_balance's own default) for every
	other caller here, which only ever prices a single, first-of-the-day run.
	"""
	day = getdate(posting_date)
	short = []
	for line in lines:
		required = flt(line["required_qty"])
		if required <= 0:
			continue
		warehouse = line["source_warehouse"]
		if not warehouse:
			continue
		have = flt(get_stock_balance(line["item_code"], warehouse, day, posting_time))
		if have + 1e-9 < required:
			short.append(
				{
					"item_code": line["item_code"],
					"item_name": line["item_name"],
					"warehouse": warehouse,
					"required": required,
					"available": have,
					"short": required - have,
					"uom": line["uom"] or "",
				}
			)
	return short


def shortfalls_on(bom_no, total_qty, posting_date, posting_time=None):
	"""Rows the stores could not cover on `posting_date` (at `posting_time`,
	when given — see `_short_lines_on`). Read-only."""
	_bom, lines = resolve_requirement(bom_no, total_qty)
	return _short_lines_on(lines, posting_date, posting_time)


def _earliest_workable_date_for_lines(lines, from_date, to_date):
	"""Same walk as `earliest_workable_date`, over already-resolved `lines`."""
	day = getdate(from_date)
	last = getdate(to_date)
	while day <= last:
		if not _short_lines_on(lines, day):
			return str(day)
		day = getdate(add_days(day, 1))
	return None


def earliest_workable_date(bom_no, total_qty, from_date, to_date):
	"""The first day in the range on which every line is covered, or None.

	Walks forward rather than back: the answer a user needs is the earliest day
	that works, and stock generally accumulates, so the first hit is the answer.
	Resolves the requirement once, up front, then reprices each candidate day
	against those same lines.
	"""
	_bom, lines = resolve_requirement(bom_no, total_qty)
	return _earliest_workable_date_for_lines(lines, from_date, to_date)


def assert_can_cover_on(bom_no, total_qty, posting_date, posting_time=None):
	"""Throw a message a farm worker can act on, or return silently.

	`posting_time` — see `_short_lines_on` — must be the exact time this run is
	about to post at when a same-day run has already gone out; otherwise this
	check and what actually posts are answering slightly different questions.
	"""
	_bom, lines = resolve_requirement(bom_no, total_qty)
	short = _short_lines_on(lines, posting_date, posting_time)
	if not short:
		return

	lines_msg = "\n".join(
		_("{0}: needed {1:,.2f} {2}, store held {3:,.2f}, short {4:,.2f} {2}").format(
			row["item_name"], row["required"], row["uom"], row["available"], row["short"]
		)
		for row in short
	)
	workable = _earliest_workable_date_for_lines(
		lines, posting_date, add_days(getdate(posting_date), SEARCH_DAYS)
	)
	when = (
		_("Earliest date this run works: {0}.").format(workable)
		if workable
		else _("No date in the next {0} days covers it.").format(SEARCH_DAYS)
	)
	frappe.throw(
		_("This feed run cannot post on {0}.\n\n{1}\n\n{2}\n\nNothing was posted.").format(
			getdate(posting_date), lines_msg, when
		),
		title=_("Not enough stock on that day"),
	)
