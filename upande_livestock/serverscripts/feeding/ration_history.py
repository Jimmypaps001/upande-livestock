"""Which recipe each herd was fed, on what day, how much of it — and the milk
that followed.

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

**Milk is placed beside the ration, never divided by it.** Milk does not come
from one day's feed — it comes from weeks of them, from stage of lactation,
from weather, from who was milking. So this endpoint offers a window
(`milk_window`) and names it back in the response, and computes no ratio, no
yield-per-kg, nothing that would assert a causal link this data cannot carry.
Two facts side by side, each labelled with what it is.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

from upande_livestock.serverscripts.common.choices import herd_label_map
from upande_livestock.serverscripts.common.envelope import guard_read, run

# Which days' milk to read for a ration fed on day D, and what to call the
# figure that comes back. Nothing here is a claim about lag — the farm picks
# the window, and the label travels with the number so a screen cannot show a
# next-day figure under a same-day heading.
MILK_WINDOWS = {
	"same_day": ((0,), "milk same day"),
	"next_day": ((1,), "milk next day"),
	"plus_two": ((2,), "milk two days later"),
	"avg_three": ((0, 1, 2), "3-day average (day fed, +1, +2)"),
}
DEFAULT_MILK_WINDOW = "same_day"

# An unbounded history is a slow page: this site already holds 5,168 Work
# Orders. Rows come back newest-first, so the default answers "what have we
# been feeding lately" without asking for four years of it, and `truncated`
# says plainly when there is more behind it.
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


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
	four times on 2026-08-26 — and four rows carrying the same herd-day milk
	figure invite somebody to add them up and quadruple the day's milk. Summed
	per recipe, the milk figure appears exactly once per row and `runs` still
	says how many times the mixer was loaded.

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


def _milk_by_day(herds, first, last):
	"""{(herd, date): kg} — a herd's whole day, both milkings summed.

	Milk Recording is one row per session, so a day is two rows; the figure a
	ration sits beside has to be the day, not whichever session was written
	first.
	"""
	if not herds or not first or not last:
		return {}
	placeholders = ", ".join(["%s"] * len(herds))
	rows = frappe.db.sql(
		f"""SELECT herd, recording_date, SUM(total_yield_kg) AS kg
		    FROM `tabMilk Recording`
		    WHERE docstatus = 1
		      AND herd IN ({placeholders})
		      AND recording_date BETWEEN %s AND %s
		    GROUP BY herd, recording_date""",
		[*herds, str(first), str(last)],
		as_dict=True,
	)
	return {(r.herd, getdate(r.recording_date)): flt(r.kg) for r in rows}


def _milk_for(by_day, herd, fed_on, offsets, averaged):
	"""(kg, days_counted) for one ration row, or (None, 0) with nothing recorded.

	An average is taken over the days that were actually recorded, not over
	three regardless: this farm records milk on some days and not others, and
	dividing one recorded day by three would report a third of the milk it
	got. `days` travels with the number so a reader can see how thin it is.
	"""
	vals = []
	for off in offsets:
		kg = by_day.get((herd, add_days(fed_on, off)))
		if kg is not None:
			vals.append(kg)
	if not vals:
		return None, 0
	if averaged:
		return round(sum(vals) / len(vals), 1), len(vals)
	return round(vals[0], 1), 1


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
	labels = herd_label_map()
	return [{"herd": r.custom_herd, "label": labels.get(r.custom_herd, r.custom_herd)} for r in rows]


@frappe.whitelist()
def ration_history(herd=None, from_date=None, to_date=None, milk_window=None, limit=None):
	"""The ration record: recipe, herd, day, quantity — and the milk beside it.

	`milk_window` chooses which day's milk sits next to a ration:
	`same_day`, `next_day`, `plus_two`, or `avg_three`. The response repeats
	the window and its label back, so a page cannot print a next-day figure
	under a same-day heading.

	`herd` narrows to one herd, `from_date`/`to_date` to a span (inclusive,
	swapped if given backwards), `limit` bounds the answer — newest first,
	with `truncated` set when there is more history than was asked for.
	"""

	def go():
		guard_read("Work Order")

		window = (milk_window or DEFAULT_MILK_WINDOW).strip()
		if window not in MILK_WINDOWS:
			frappe.throw(
				_("Unknown milk window {0}. Choose one of: {1}.").format(
					window, ", ".join(sorted(MILK_WINDOWS))
				)
			)
		offsets, window_label = MILK_WINDOWS[window]

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
		# Reach forward far enough for the widest window; a ration fed on the
		# last day still needs its +2 milk.
		milk_last = add_days(last, max(offsets)) if last else None

		# Milk is a separate doctype with its own permissions. A user who may
		# read feed runs but not milk records gets the ration history with the
		# milk column blank and told why, rather than either a leak or a
		# locked page.
		milk_visible = frappe.has_permission("Milk Recording", "read")
		by_day = _milk_by_day(herds, first, milk_last) if milk_visible else {}
		modes = _feed_modes(herds, first, last)
		labels = herd_label_map()
		averaged = len(offsets) > 1

		out = []
		for r in rows:
			kg, milk_days = _milk_for(by_day, r["herd"], r["fed_on"], offsets, averaged)
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
					"qty": flt(r["qty"]),
					"uom": r["uom"] or "",
					"runs": int(r["runs"]),
					"heads": int(r["heads"] or 0),
					"feed_mode": modes.get((r["herd"], r["fed_on"]), ""),
					"milk_kg": kg,
					"milk_days": milk_days,
				}
			)

		return {
			"ok": True,
			"rows": out,
			"herds": _herds_with_history(),
			"milk_window": window,
			"milk_window_label": window_label,
			"milk_visible": milk_visible,
			"windows": [
				{"value": key, "label": label} for key, (_offsets, label) in MILK_WINDOWS.items()
			],
			"herd": herd or "",
			"from_date": str(f) if f else "",
			"to_date": str(t) if t else "",
			"limit": cap,
			"truncated": truncated,
		}

	return run(go, "livestock ration_history failed")
