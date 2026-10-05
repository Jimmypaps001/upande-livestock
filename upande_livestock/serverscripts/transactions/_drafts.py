# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The livestock stock entries, and what each draft is waiting for.

An event recorded today when the store could not cover it saves its issue as a
draft (common/stock). The Transactions page shows those drafts, a calendar of
which days have drafts and which only posted entries, and any one day's
entries: what was used, by which record, and — for a draft — whether the store
can cover it now.
"""

import frappe
from frappe.utils import get_fullname

from upande_livestock.serverscripts.common import stock as livestock_stock

# Where each record keeps the issue it made.
SOURCES = (
	("Livestock Event", "stock_entry", ["event_type", "animal", "current_herd"]),
	("Livestock Diagnosis", "stock_entry", ["animal"]),
	("Livestock Health Case", "drug_stock_entry", ["animal"]),
)
MIX_TYPES = ("Ration Mixing", "Concentrate Mixing")


def _source(doctype, r):
	return {
		"doctype": doctype,
		"name": r.name,
		"animal": r.get("animal"),
		"herd": r.get("current_herd"),
		"event_type": r.get("event_type") or doctype.replace("Livestock ", ""),
	}


def _sources(entries):
	names = [e.name for e in entries]
	found = {}
	for doctype, field, extra in SOURCES:
		if not frappe.db.has_column(doctype, field):
			continue
		for r in frappe.get_all(
			doctype,
			filters={field: ["in", names], "docstatus": ["<", 2]},
			fields=["name", field, *extra],
		):
			found.setdefault(r[field], _source(doctype, r))
	# A feed run's transfer and mix belong to the Feeding that gave it out.
	orders = {e.work_order for e in entries if e.get("work_order")}
	if orders and frappe.db.has_column("Livestock Event", "feed_work_order"):
		by_order = {
			r.feed_work_order: _source("Livestock Event", r)
			for r in frappe.get_all(
				"Livestock Event",
				filters={"feed_work_order": ["in", list(orders)], "docstatus": ["<", 2]},
				fields=["name", "feed_work_order", "event_type", "current_herd"],
			)
		}
		for e in entries:
			if e.name not in found and e.get("work_order") in by_order:
				found[e.name] = by_order[e.work_order]
	return found


def _livestock_where(alias="se"):
	"""SQL picking this app's Stock Entries: its named types, and the transfer
	leg of a feed run, whose type is ERPNext's generic one. A feed run's
	transfer is known by its Work Order — a herd's ration (custom_herd), or one
	whose mix posted under a mixing type."""
	feed_orders = [
		f"SELECT m.work_order FROM `tabStock Entry` m WHERE m.stock_entry_type IN %(mix_types)s "
		f"AND m.docstatus < 2 AND IFNULL(m.work_order, '') != ''"
	]
	if frappe.db.has_column("Work Order", "custom_herd"):
		feed_orders.append("SELECT w.name FROM `tabWork Order` w WHERE IFNULL(w.custom_herd, '') != ''")
	return (
		f"({alias}.stock_entry_type IN %(types)s OR ({alias}.purpose = 'Material Transfer for Manufacture' "
		f"AND {alias}.work_order IN ({' UNION '.join(feed_orders)})))"
	)


def _args(**more):
	return {"types": livestock_stock.livestock_stock_entry_types(), "mix_types": MIX_TYPES, **more}


def _label(e):
	if e.purpose != "Material Transfer for Manufacture":
		return e.stock_entry_type
	return "Feed run · waiting to mix" if e.docstatus == 0 else "Feed transfer"


def is_livestock_draft(name):
	if not name:
		return False
	return bool(
		frappe.db.sql(
			f"SELECT se.name FROM `tabStock Entry` se WHERE se.name = %(name)s AND se.docstatus = 0 "
			f"AND {_livestock_where()}",
			_args(name=name),
		)
	)


def entry_rows(where="", args=None):
	"""The livestock Stock Entries matching `where` (drafts and posted)."""
	entries = frappe.db.sql(
		f"""SELECT se.name, se.docstatus, se.posting_date, se.stock_entry_type, se.purpose, se.work_order,
		           se.remarks, se.owner, se.creation
		    FROM `tabStock Entry` se
		    WHERE se.docstatus < 2 AND {_livestock_where()} {where}
		    ORDER BY se.posting_date DESC, se.creation DESC
		    LIMIT 500""",
		_args(**(args or {})),
		as_dict=True,
	)
	if not entries:
		return []
	names = [e.name for e in entries]
	items = {}
	for d in frappe.get_all(
		"Stock Entry Detail",
		filters={"parent": ["in", names], "parenttype": "Stock Entry"},
		fields=["parent", "item_code", "item_name", "qty", "uom", "s_warehouse", "t_warehouse"],
		order_by="idx asc",
	):
		items.setdefault(d.parent, []).append(d)
	sources = _sources(entries)

	out = []
	for e in entries:
		rows = items.get(e.name, [])
		draft = e.docstatus == 0
		# Only a draft is waiting on the store; a posted entry already took it.
		short = (
			livestock_stock.check_availability(
				[{"item_code": r.item_code, "warehouse": r.s_warehouse, "qty": r.qty} for r in rows if r.s_warehouse]
			)
			if draft
			else []
		)
		out.append(
			{
				"name": e.name,
				"status": "Draft" if draft else "Posted",
				"posting_date": str(e.posting_date),
				"stock_entry_type": e.stock_entry_type,
				"label": _label(e),
				"remarks": e.remarks,
				"made_by": get_fullname(e.owner),
				"source": sources.get(e.name),
				"items": [
					{
						"item_code": r.item_code,
						"item_name": r.item_name,
						"qty": r.qty,
						"uom": r.uom,
						"warehouse": r.s_warehouse or r.t_warehouse,
					}
					for r in rows
				],
				"can_post": draft and not short,
				"short": livestock_stock.shortage_message(short) if short else None,
			}
		)
	return out


def draft_rows():
	return entry_rows("AND se.docstatus = 0")


def day_counts(from_date, to_date):
	"""{date: {"draft": n, "posted": n}} for the days in range with any entry."""
	rows = frappe.db.sql(
		f"""SELECT se.posting_date, se.docstatus, COUNT(*) AS n FROM `tabStock Entry` se
		    WHERE se.docstatus < 2 AND {_livestock_where()}
		      AND se.posting_date BETWEEN %(from)s AND %(to)s
		    GROUP BY se.posting_date, se.docstatus""",
		_args(**{"from": from_date, "to": to_date}),
		as_dict=True,
	)
	days = {}
	for r in rows:
		day = days.setdefault(str(r.posting_date), {"draft": 0, "posted": 0})
		day["draft" if r.docstatus == 0 else "posted"] += r.n
	return days
