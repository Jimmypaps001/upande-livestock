"""Which recipe each herd was fed, on what day, and how much of it.

The record of "this herd was fed this recipe on this day" is the Work Order.
Nothing new is stored for this page: `custom_herd`, `custom_no_of_cows`,
`bom_no`, `qty` and `planned_start_date` are already on every mix run the
feeding engine submits, and together they are the whole fact.

Two decisions in here matter more than the SQL.

**The BOM is read off the Work Order, never off `Herds.bom`.** A herd's
standing ration is edited in place — 0-2 is on BOM-TMR Calves Meal-011 today,
while every run it has ever had cites BOM-TMR Calves Meal-005. Reading the
herd's *present* BOM would silently rewrite the whole history every time
somebody tunes a recipe, and the page would claim the farm has been feeding
today's mix since March. The Work Order remembers what was actually used, so
that is what is reported.

**Every row carries the recipe's own lines.** An operator opening a day wants
to know what went in the mixer, and the answer has to be in the units the
recipe is written in — `BOM Item.qty`/`.uom`, never `stock_qty`/`stock_uom`.
Hay is 5 kg on every herd BOM here but stocked in BALE at a conversion factor
of 0.07, so the stock figure would show a fourteenth of the hay. The lines for
every distinct recipe on the page are fetched in ONE query (`_recipe_lines`),
not per row: the page returns up to a thousand rows and the same recipe fills
most of them.

**Days before the app are tracker history, and say so.** Mutara fed for a year
on its spreadsheet; those days are Livestock Feed History records with no Work
Order and no stock behind them. They join the page as rows with
`from_history` set, no BOM, and the kilograms the sheet recorded — and only for
a herd-day no Work Order covers, the same rule cost per animal keeps, so one
day is never shown twice.
"""

from itertools import groupby

import frappe
from frappe.utils import add_days, flt, getdate

from upande_livestock.serverscripts.common.choices import herd_label_map
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.gain import herd_period_gain
from upande_livestock.serverscripts.feeding import _recipe_lines

# An unbounded history is a slow page: this site already holds 5,168 Work
# Orders. Rows come back newest-first, so the default answers "what have we
# been feeding lately" without asking for four years of it, and `truncated`
# says plainly when there is more behind it.
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000

HISTORY_DOCTYPE = "Livestock Feed History"
HISTORY_ITEM_DOCTYPE = "Livestock Feed History Item"
HISTORY_RECIPE = "Tracker history"


def _bounds(from_date, to_date):
	"""(from, to) as dates, either may be None. Reversed input is swapped
	rather than refused — a picker set back-to-front should show the range
	between the two dates, not an empty table."""
	f = getdate(from_date) if from_date else None
	t = getdate(to_date) if to_date else None
	if f and t and f > t:
		f, t = t, f
	return f, t


def _ration_rows(herd, from_date, to_date, limit):
	"""One row per (day, herd, recipe), not per Work Order.

	A herd's day is mixed in more than one run — the calves' 45 kg went out
	four times on 2026-08-26 — and four rows for one herd-day invite somebody to
	count the day four times. Summed per recipe, each recipe appears once per day
	and `runs` still says how many times the mixer was loaded.

	`docstatus = 1` only: a draft Work Order is a mix somebody is still
	planning and a cancelled one never happened. Neither is a record of a herd
	being fed.
	"""
	conditions = ["IFNULL(wo.custom_herd, '') <> ''", "wo.docstatus = 1"]
	params = []
	if herd:
		conditions.append("wo.custom_herd = %s")
		params.append(herd)
	# Compared as a datetime range rather than DATE(planned_start_date), so the
	# column's index still applies; the day-grouping below can afford DATE().
	if from_date:
		conditions.append("wo.planned_start_date >= %s")
		params.append(str(from_date))
	if to_date:
		conditions.append("wo.planned_start_date < %s")
		params.append(str(add_days(to_date, 1)))

	return frappe.db.sql(
		"""SELECT DATE(wo.planned_start_date) AS fed_on,
		          wo.custom_herd AS herd,
		          wo.bom_no AS bom_no,
		          wo.production_item AS item_code,
		          MAX(bom.item_name) AS bom_item_name,
		          MAX(bom.custom_ration_kind) AS ration_kind,
		          MAX(wo.stock_uom) AS uom,
		          SUM(wo.qty) AS qty,
		          MAX(wo.custom_no_of_cows) AS heads,
		          COUNT(*) AS runs
		   FROM `tabWork Order` wo
		   LEFT JOIN `tabBOM` bom ON bom.name = wo.bom_no
		   WHERE """
		+ " AND ".join(conditions)
		+ """
		   GROUP BY DATE(wo.planned_start_date), wo.custom_herd, wo.bom_no, wo.production_item
		   ORDER BY fed_on DESC, wo.custom_herd ASC, wo.bom_no ASC
		   LIMIT %s""",
		[*params, limit + 1],
		as_dict=True,
	)


def _feed_modes(herds, first, last):
	"""{(herd, date): "System" | "Manual" | "System, Manual"}.

	Matched on herd and day, not by document link: the Feeding event carries
	the *issue* Stock Entry, which is a different document from the Work Order
	that mixed the ration, so there is no key joining the two. A herd-day match
	is what the data supports, and a Work Order with no event beside it keeps
	its row with an empty mode rather than disappearing — the mix happened
	either way.
	"""
	if not herds or not first or not last:
		return {}
	placeholders = ", ".join(["%s"] * len(herds))
	rows = frappe.db.sql(
		f"""SELECT current_herd AS herd, event_date, custom_feed_mode AS mode
		    FROM `tabLivestock Event`
		    WHERE event_type = 'Feeding'
		      AND docstatus = 1
		      AND current_herd IN ({placeholders})
		      AND event_date BETWEEN %s AND %s""",
		[*herds, str(first), str(last)],
		as_dict=True,
	)
	modes = {}
	for r in rows:
		if not r.mode:
			continue
		modes.setdefault((r.herd, getdate(r.event_date)), set()).add(r.mode)
	return {key: ", ".join(sorted(found)) for key, found in modes.items()}


def _ration_periods(herds):
	"""{(herd, day, bom_no): (start, end)} — the period each fed row belongs to.

	A period is a run of the herd's consecutive feed days on which that recipe
	was fed; it ends on the first feed day of the herd where the recipe is
	absent. "Consecutive" means consecutive feed days, not calendar days: a
	skipped day with no feeding at all does not end a run, a day fed on another
	recipe does. A herd fed two recipes every day therefore has two long
	overlapping periods, one per recipe.

	Read from every submitted Work Order of those herds, not from the page's
	rows, so a page cut by a date filter or the row limit still reports the
	whole period's gain.
	"""
	if not herds:
		return {}
	rows = frappe.db.sql(
		"""SELECT DISTINCT custom_herd AS herd, DATE(planned_start_date) AS day, bom_no
		   FROM `tabWork Order`
		   WHERE docstatus = 1 AND custom_herd IN %(herds)s
		   ORDER BY custom_herd, day, bom_no""",
		{"herds": tuple(herds)},
		as_dict=True,
	)
	periods = {}
	for herd, herd_rows in groupby(rows, key=lambda r: r.herd):
		by_day = {}
		for r in herd_rows:
			by_day.setdefault(getdate(r.day), set()).add(r.bom_no)
		open_run = {}  # bom_no -> [start, end]
		for day in sorted(by_day):
			for bom in list(open_run):
				if bom not in by_day[day]:
					start, end = open_run.pop(bom)
					_close_run(periods, herd, bom, start, end, by_day)
			for bom in by_day[day]:
				open_run.setdefault(bom, [day, day])[1] = day
		for bom, (start, end) in open_run.items():
			_close_run(periods, herd, bom, start, end, by_day)
	return periods


def _close_run(periods, herd, bom, start, end, by_day):
	for day, boms in by_day.items():
		if start <= day <= end and bom in boms:
			periods[(herd, day, bom)] = (start, end)


def _wo_herd_days(herds, first, last):
	"""{(herd, day)} with a submitted mix run: the herd-days tracker history must not repeat."""
	if not herds or not first or not last:
		return set()
	rows = frappe.db.sql(
		"""SELECT DISTINCT custom_herd AS herd, DATE(planned_start_date) AS day
		   FROM `tabWork Order`
		   WHERE docstatus = 1 AND custom_herd IN %(herds)s
		     AND planned_start_date >= %(lo)s AND planned_start_date < %(hi)s""",
		{"herds": tuple(herds), "lo": str(first), "hi": str(add_days(last, 1))},
		as_dict=True,
	)
	return {(r.herd, getdate(r.day)) for r in rows}


def _tracker_rows(herd, from_date, to_date, limit, labels):
	"""Livestock Feed History as page rows, newest first, marked `from_history`.

	The sheet's kilograms per feed are the row's lines, in kg; there is no BOM
	because nothing was mixed through the app. A herd-day a Work Order covers is
	left to the Work Order.
	"""
	if not frappe.db.table_exists(HISTORY_DOCTYPE):
		return []
	filters = {}
	if herd:
		filters["herd"] = herd
	if from_date and to_date:
		filters["date"] = ["between", [str(from_date), str(to_date)]]
	elif from_date:
		filters["date"] = [">=", str(from_date)]
	elif to_date:
		filters["date"] = ["<=", str(to_date)]
	rows = frappe.get_all(
		HISTORY_DOCTYPE, filters=filters,
		fields=["name", "date", "herd", "head_count", "total_kg", "source"],
		order_by="date desc, herd asc", limit=limit + 1,
	)
	if not rows:
		return []
	days = [getdate(r.date) for r in rows]
	mixed = _wo_herd_days(sorted({r.herd for r in rows}), min(days), max(days))
	rows = [r for r in rows if (r.herd, getdate(r.date)) not in mixed]
	if not rows:
		return []
	lines = {}
	for ln in frappe.get_all(
		HISTORY_ITEM_DOCTYPE,
		filters={"parenttype": HISTORY_DOCTYPE, "parent": ["in", [r.name for r in rows]]},
		fields=["parent", "item", "qty_kg", "idx"], order_by="parent asc, idx asc", limit=0,
	):
		lines.setdefault(ln.parent, []).append(
			{"item_code": ln.item, "item_name": ln.item, "qty": flt(ln.qty_kg), "uom": "Kg",
			 "is_concentrate": False, "is_dose": False}
		)
	out = []
	for r in rows:
		day = getdate(r.date)
		out.append({
			"fed_on": str(day),
			"herd": r.herd,
			"herd_label": labels.get(r.herd, r.herd),
			"bom_no": "",
			"item_code": "",
			"recipe": HISTORY_RECIPE,
			"ration_kind": "",
			"lines": lines.get(r.name, []),
			"qty": flt(r.total_kg),
			"uom": "Kg",
			"runs": 0,
			"heads": int(r.head_count or 0),
			"feed_mode": "",
			"avg_adg_kg": None,
			"weighed_head": 0,
			"period_start": str(day),
			"period_end": str(day),
			"from_history": True,
			"history_source": r.source or "",
		})
	return out


def _herds_with_history():
	"""Every herd that appears anywhere in the ration history, for the filter.

	Read from the Work Orders rather than from Herds: a herd renamed since
	(`Bullying Heifers`, `In calf heifers`) still owns rows here, and a filter
	built from the current herd list could not reach them.
	"""
	rows = frappe.db.sql(
		"""SELECT DISTINCT custom_herd FROM `tabWork Order`
		   WHERE IFNULL(custom_herd, '') <> '' AND docstatus = 1
		   ORDER BY custom_herd""",
		as_dict=True,
	)
	names = {r.custom_herd for r in rows}
	if frappe.db.table_exists(HISTORY_DOCTYPE):
		names.update(frappe.get_all(HISTORY_DOCTYPE, pluck="herd", distinct=True, limit=0))
	labels = herd_label_map()
	return [{"herd": h, "label": labels.get(h, h)} for h in sorted(n for n in names if n)]


@frappe.whitelist()
def ration_history(herd=None, from_date=None, to_date=None, limit=None):
	"""The ration record: recipe, herd, day, quantity.

	`herd` narrows to one herd, `from_date`/`to_date` to a span (inclusive,
	swapped if given backwards), `limit` bounds the answer — newest first,
	with `truncated` set when there is more history than was asked for.
	"""

	def go():
		guard_read("Work Order")

		try:
			cap = int(limit) if limit else DEFAULT_LIMIT
		except (TypeError, ValueError):
			cap = DEFAULT_LIMIT
		cap = max(1, min(cap, MAX_LIMIT))

		f, t = _bounds(from_date, to_date)
		rows = _ration_rows(herd, f, t, cap)
		truncated = len(rows) > cap
		rows = rows[:cap]

		for r in rows:
			r["fed_on"] = getdate(r["fed_on"])

		herds = sorted({r["herd"] for r in rows})
		days = [r["fed_on"] for r in rows]
		first, last = (min(days), max(days)) if days else (None, None)
		modes = _feed_modes(herds, first, last)
		labels = herd_label_map()
		# One query for every distinct recipe on the page, however many rows
		# cite it — see the module docstring.
		lines_by_bom = _recipe_lines.lines_for([r["bom_no"] for r in rows])

		periods = _ration_periods(herds)
		gains = {}
		out = []
		for r in rows:
			span = periods.get((r["herd"], r["fed_on"], r["bom_no"]), (r["fed_on"], r["fed_on"]))
			if (r["herd"], span) not in gains:
				gains[(r["herd"], span)] = herd_period_gain(r["herd"], *span)
			avg_adg, weighed_head = gains[(r["herd"], span)]
			out.append(
				{
					"fed_on": str(r["fed_on"]),
					"herd": r["herd"],
					"herd_label": labels.get(r["herd"], r["herd"]),
					"bom_no": r["bom_no"],
					"item_code": r["item_code"],
					# The BOM's own item name reads as a recipe; the bom_no is
					# kept beside it because that is what distinguishes -005
					# from -011, and it is the only thing that does.
					"recipe": r["bom_item_name"] or r["item_code"] or r["bom_no"],
					"ration_kind": r["ration_kind"] or "",
					# In RECIPE qty/uom. See the module docstring.
					"lines": lines_by_bom.get(r["bom_no"], []),
					"qty": flt(r["qty"]),
					"uom": r["uom"] or "",
					"runs": int(r["runs"]),
					"heads": int(r["heads"] or 0),
					"feed_mode": modes.get((r["herd"], r["fed_on"]), ""),
					# Gain of the herd's animals over the whole stretch on this
					# recipe; None (not 0) when too few were weighed to say.
					"avg_adg_kg": round(avg_adg, 3) if avg_adg is not None else None,
					"weighed_head": weighed_head,
					# The period those two figures belong to, so a reader can count
					# each period once rather than once per day row.
					"period_start": str(span[0]),
					"period_end": str(span[1]),
					"from_history": False,
				}
			)

		# Tracker history for the herd-days no mix run covers, merged in date order.
		history = _tracker_rows(herd, f, t, cap, labels)
		truncated = truncated or len(history) > cap
		out = sorted(out + history[:cap], key=lambda r: r["fed_on"], reverse=True)
		truncated = truncated or len(out) > cap
		out = out[:cap]

		return {
			"ok": True,
			"rows": out,
			"herds": _herds_with_history(),
			"herd": herd or "",
			"from_date": str(f) if f else "",
			"to_date": str(t) if t else "",
			"limit": cap,
			"truncated": truncated,
		}

	return run(go, "livestock ration_history failed")
