"""Can this feed run post on that day, and if not, when could it?

`_engine.resolve_requirement` prices a run against `Bin`, which holds today's
balance and nothing else. A backdated run has to be judged against the ledger as
it stood on the day, which is what `get_stock_balance` answers.

Relying on ERPNext's own NegativeStockError instead was tried and is not good
enough for this screen: it names the first item it trips over, gives no date, and
by the time it fires a Work Order and a transfer have already been written and
have to be rolled back. This runs first and writes nothing.
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


def shortfalls_on(bom_no, total_qty, posting_date):
	"""Rows the stores could not cover on `posting_date`. Read-only."""
	_bom, lines = resolve_requirement(bom_no, total_qty)
	day = getdate(posting_date)
	short = []
	for line in lines:
		required = flt(line["required_qty"])
		if required <= 0:
			continue
		warehouse = line["source_warehouse"]
		if not warehouse:
			continue
		have = flt(get_stock_balance(line["item_code"], warehouse, day))
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


def earliest_workable_date(bom_no, total_qty, from_date, to_date):
	"""The first day in the range on which every line is covered, or None.

	Walks forward rather than back: the answer a user needs is the earliest day
	that works, and stock generally accumulates, so the first hit is the answer.
	"""
	day = getdate(from_date)
	last = getdate(to_date)
	while day <= last:
		if not shortfalls_on(bom_no, total_qty, day):
			return str(day)
		day = getdate(add_days(day, 1))
	return None


def assert_can_cover_on(bom_no, total_qty, posting_date):
	"""Throw a message a farm worker can act on, or return silently."""
	short = shortfalls_on(bom_no, total_qty, posting_date)
	if not short:
		return

	lines = "\n".join(
		_("{0}: needed {1:,.2f} {2}, store held {3:,.2f}").format(
			row["item_name"], row["required"], row["uom"], row["available"]
		)
		for row in short
	)
	workable = earliest_workable_date(
		bom_no, total_qty, posting_date, add_days(getdate(posting_date), SEARCH_DAYS)
	)
	when = (
		_("Earliest date this run works: {0}.").format(workable)
		if workable
		else _("No date in the next {0} days covers it.").format(SEARCH_DAYS)
	)
	frappe.throw(
		_("This feed run cannot post on {0}.\n\n{1}\n\n{2}\n\nNothing was posted.").format(
			getdate(posting_date), lines, when
		),
		title=_("Not enough stock on that day"),
	)
