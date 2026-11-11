# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the cost report reads from the site: the stock ledger, the labour
book, the animals and the shoat counts.

Cost is the **stock ledger's** value, never a price list (decided with the farm
on 2026-11-11). A feed issue costs what ERPNext moved out of the store at
valuation — `-stock_value_difference` on its outgoing ledger rows — so this
report and the farm's balance sheet cannot disagree. A cancelled entry's rows
are `is_cancelled` and drop out on their own; a draft (fed while the store was
short) has no ledger rows yet and costs nothing until it posts.
"""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common import cost_center as livestock_cost_center
from upande_livestock.serverscripts.common import herd_history
from upande_livestock.serverscripts.common import shoats
from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.costing import _maths

LABOUR_DOCTYPE = "Livestock Daily Labour"
LABOUR_ROW_DOCTYPE = "Livestock Daily Labour Entry"

#: Livestock stock entry types that are not medicine: the feed (counted per
#: herd) and the two mixes (whose value reaches a herd through the feed issue
#: that follows — counting the mix too would count the feed twice), and the
#: semen a service uses, which is breeding, not treatment.
NOT_MEDICINE = {
	livestock_stock.STOCK_ENTRY_TYPES["Feeding"],
	livestock_stock.STOCK_ENTRY_TYPES["Concentrate Manufacture"],
	livestock_stock.STOCK_ENTRY_TYPES["Ration Manufacture"],
	livestock_stock.event_stock_entry_type("Service"),
	"Semen Issue",
}


def herd_names():
	return frappe.get_all("Herds", pluck="name", limit=0)


def _issues(lo, hi, extra_where, args):
	"""Outgoing value per submitted Material Issue, from the stock ledger."""
	return frappe.db.sql(
		f"""SELECT se.name, se.posting_date, se.remarks, se.stock_entry_type,
		           SUM(-sle.stock_value_difference) AS value
		    FROM `tabStock Ledger Entry` sle
		    JOIN `tabStock Entry` se ON se.name = sle.voucher_no
		    WHERE sle.voucher_type = 'Stock Entry'
		      AND sle.is_cancelled = 0
		      AND sle.actual_qty < 0
		      AND se.docstatus = 1
		      AND se.purpose = 'Material Issue'
		      AND {extra_where}
		    GROUP BY se.name, se.posting_date, se.remarks, se.stock_entry_type""",
		{"lo": lo, "hi": hi, **args},
		as_dict=True,
	)


def feed_by_herd(lo, hi):
	"""{herd: {day: cost}} — feed issued to each herd, on the day it was eaten.

	A run that waited for stock posts later with "- fed <day>" in its remark
	(`feeding/_engine._post_feed_issue`); it is costed on the day the herd ate
	it, as the feed day screen counts it. So the query also takes such runs
	posted after the window, and drops runs eaten before it.
	"""
	rows = _issues(
		lo, hi,
		"""se.remarks LIKE %(prefix)s
		   AND se.posting_date >= %(lo)s
		   AND (se.posting_date <= %(hi)s OR se.remarks LIKE %(fed)s)""",
		{"prefix": _maths.FEED_PREFIX + "%", "fed": "% - fed %"},
	)
	herds = herd_names()
	lo_d, hi_d = _maths.as_date(lo), _maths.as_date(hi)
	out = {}
	for r in rows:
		herd = _maths.herd_of_feed(r.remarks, herds)
		day = _maths.fed_day(r.remarks, r.posting_date)
		if not herd or day < lo_d or day > hi_d:
			continue
		by_day = out.setdefault(herd, {})
		by_day[day] = by_day.get(day, 0.0) + flt(r.value)
	return out


def medicine_by_day(lo, hi):
	"""{day: cost} — drugs and vet supplies the livestock flows issued.

	Every stock entry type this app posts under (`common.stock.
	livestock_stock_entry_types`: the events', the shoat treatments', and the
	old names) except the feed, the mixes and semen. Spread over every animal
	like labour: a deworming round is a farm cost, not one herd's.
	"""
	types = [t for t in livestock_stock.livestock_stock_entry_types() if t not in NOT_MEDICINE]
	if not types:
		return {}
	rows = _issues(
		lo, hi,
		"""se.stock_entry_type IN %(types)s
		   AND se.remarks NOT LIKE %(prefix)s
		   AND se.posting_date BETWEEN %(lo)s AND %(hi)s""",
		{"types": tuple(types), "prefix": _maths.FEED_PREFIX + "%"},
	)
	out = {}
	for r in rows:
		day = _maths.as_date(r.posting_date)
		out[day] = out.get(day, 0.0) + flt(r.value)
	return out


def labour_by_day(lo, hi):
	"""{day: amount} — summed from the rows, not the stored total, so an edited
	row is never out of step with a total nobody re-saved."""
	if not frappe.db.table_exists(LABOUR_DOCTYPE):
		return {}
	rows = frappe.db.sql(
		f"""SELECT l.labour_date AS day, SUM(e.amount) AS amount
		    FROM `tab{LABOUR_DOCTYPE}` l
		    JOIN `tab{LABOUR_ROW_DOCTYPE}` e ON e.parent = l.name AND e.parenttype = %(dt)s
		    WHERE l.labour_date BETWEEN %(lo)s AND %(hi)s
		    GROUP BY l.labour_date""",
		{"lo": lo, "hi": hi, "dt": LABOUR_DOCTYPE},
		as_dict=True,
	)
	return {_maths.as_date(r.day): flt(r.amount) for r in rows}


def default_rates():
	"""{category: rate} from Livestock Settings; a rate never set is 0, and the page says so."""
	out = {}
	for category, field in _maths.RATE_FIELDS.items():
		try:
			out[category] = flt(frappe.db.get_single_value("Livestock Settings", field))
		except Exception:
			out[category] = 0.0
	return out


def livestock_cost_centers():
	"""The cost centres the herds book to: each herd's own, the per-company
	defaults and the concentrate's. Machine work charged to any of them is the
	feedlot's (Part A charges a feedlot allocation to the livestock centre)."""
	names = set(n for n in frappe.get_all("Herds", filters={"cost_center": ["is", "set"]}, pluck="cost_center", limit=0) if n)
	try:
		names.update(
			n for n in frappe.get_all(
				livestock_cost_center.SETTINGS_TABLE_DOCTYPE,
				filters={"parenttype": livestock_cost_center.SETTINGS, "parentfield": livestock_cost_center.SETTINGS_TABLE},
				pluck="cost_center", limit=0,
			) if n
		)
	except Exception:
		pass
	try:
		cc = frappe.db.get_single_value(livestock_cost_center.SETTINGS, livestock_cost_center.CONCENTRATE_SETTING)
		if cc:
			names.add(cc)
	except Exception:
		pass
	return sorted(names)


# ---------------------------------------------------------------------------
# who was on the farm
# ---------------------------------------------------------------------------


def _exit_days(animals):
	"""{animal: the day it left}. The submitted disposal's date; for an animal
	marked gone with no disposal behind it (retired by hand, or before
	disposals existed), the day its record last changed — the best evidence
	there is, and better than counting it forever."""
	out = {}
	for r in frappe.get_all(
		"Livestock Disposal", filters={"docstatus": 1, "disposal_date": ["is", "set"]},
		fields=["animal", "disposal_date"], limit=0,
	):
		if r.animal and (r.animal not in out or r.disposal_date < out[r.animal]):
			out[r.animal] = r.disposal_date
	for name, row in animals.items():
		if name not in out and (row.status or "Active") != "Active":
			out[name] = row.modified.date() if hasattr(row.modified, "date") else row.modified
	return out


def individuals(days):
	"""({day: animals on the farm}, {herd: {day: head}}) for animals kept one by one.

	On the farm from arrival (acquisition date, else birth) until the day it
	left. Its herd on each day comes from its Movement events
	(`common.herd_history`), cut short at the day it left.
	"""
	filters = {"docstatus": ["<", 2]}
	# A disabled animal is not on the farm: it is how retired records (the
	# demo herd a farm's real data replaced) are put away without deleting them.
	if frappe.get_meta("Animal").has_field("disabled"):
		filters["disabled"] = 0
	rows = {
		r.name: r
		for r in frappe.get_all(
			"Animal", filters=filters,
			fields=["name", "current_herd", "acquisition_date", "date_of_birth", "status", "modified"], limit=0,
		)
	}
	if not rows:
		farm, heads = {d: 0 for d in days}, {}
		return _add_unrecorded(days, farm, heads)
	exits = _exit_days(rows)
	moves = herd_history._moves(rows.keys())
	farm, by_herd = [], {}
	for name, row in rows.items():
		left = exits.get(name)
		farm.append(_maths.clip_stay(herd_history._start(row), None, left))
		for herd, start, end in herd_history._build(row, moves.get(name, [])):
			if herd:
				by_herd.setdefault(herd, []).append(_maths.clip_stay(start, end, left))
	heads = {herd: _maths.count_present(days, stays) for herd, stays in by_herd.items()}
	return _add_unrecorded(days, _maths.count_present(days, farm), heads)


def _add_unrecorded(days, farm, heads):
	"""Count a one-by-one herd whose animals are not recorded yet by its stored head count.

	Mutara's In-calf, Heifers and Lactating groups are fed and paid for every
	day, but their cows are not in the app as animals yet; the herd record
	carries the count the farm feeds against. Leaving them out would spread the
	day's labour over too few animals. A herd with any recorded animal is
	counted from its animals alone, and so is one whose animals were all
	retired (disabled): its stored count is theirs. The stored count has no
	history, so it is applied to every day asked about.
	"""
	for herd, number in frappe.get_all(
		"Herds", filters={"counting": ["!=", "By number"], "number_of_animals": [">", 0]},
		fields=["name", "number_of_animals"], as_list=True, limit=0,
	):
		if (herd in heads and any(heads[herd].values())) or frappe.db.exists("Animal", {"current_herd": herd}):
			continue
		heads[herd] = {d: int(number) for d in days}
		farm = {d: farm.get(d, 0) + int(number) for d in days}
	return farm, heads


def by_number(days):
	"""{herd: {day: head}} for shoat herds, replayed from their count events."""
	out = {}
	for herd in frappe.get_all("Herds", filters={"counting": "By number"}, pluck="name", limit=0):
		out[herd] = _maths.replay_heads(days, shoats.submitted(herd), shoats.apply, shoats.zero, shoats.total)
	return out
