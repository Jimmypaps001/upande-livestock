# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Feed by head count, or feed what the operator says the group ate.

Most farms on this app feed by head count: the ration is per head, the herd has
so many head, and the day's mix is the product. That stays the default and
nothing about it changes.

Mutara does not feed that way. Its feedlot manager loads the mixer for a pen
and writes down how many kilos went in; head count times the ration is a
guide, not the answer. With Livestock Settings > Feed by Head Count off, the
screens show head count x per head as a SUGGESTION and the operator types the
group's day total. That total is what is mixed, scaled from the ration's own
lines, through exactly the same Work Order path — only the quantity comes from
the person instead of from the multiplication.

The maths is two lines and lives here, pure, so the engine, Manufacture all
and the tests all agree on it.
"""

from frappe.utils import cint, flt


def feed_by_head_count_on():
	"""Is the day's mix head count x per head? Unset means yes.

	Read raw (`read_setting`) rather than through `get_single_value`, which
	would cast a never-saved Check to 0 and quietly switch every farm that has
	not run the patch over to typed totals.
	"""
	from upande_livestock.serverscripts.common.timings import read_setting

	value = read_setting("feed_by_head_count")
	return True if value in (None, "") else bool(cint(value))


def suggested_total(per_head, heads, portion=1.0):
	"""Head count x per head x portion: what the screens offer as the total."""
	return flt(per_head) * flt(heads) * (flt(portion) or 1.0)


def portion_for_total(per_head, heads, total):
	"""The share of a head-count day that `total` kg amounts to.

	The engine and the day status both speak in portions of a day, so a typed
	total is recorded as one: 600 kg for a pen whose head-count day is 800 kg
	is a 0.75 run. Nothing here caps it at 1 — a pen fed more than the
	suggestion was fed more, and that is a fact to record.
	"""
	day = flt(per_head) * flt(heads)
	if day <= 0:
		return 0.0
	return flt(total) / day


def clean_total(total):
	"""A typed total as a positive float, or None when nothing usable was typed."""
	value = flt(total)
	return value if value > 0 else None
