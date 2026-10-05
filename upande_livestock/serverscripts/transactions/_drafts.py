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
	("Livestock Event", "stock_entry", ["event_type", "animal"]),
	("Livestock Diagnosis", "stock_entry", ["animal"]),
	("Livestock Health Case", "drug_stock_entry", ["animal"]),
)


def _sources(names):
	found = {}
	for doctype, field, extra in SOURCES:
		if not frappe.db.has_column(doctype, field):
			continue
		for r in frappe.get_all(
			doctype,
			filters={field: ["in", names], "docstatus": ["<", 2]},
			fields=["name", field, *extra],
		):
			found.setdefault(
				r[field],
				{
					"doctype": doctype,
					"name": r.name,
					"animal": r.get("animal"),
					"event_type": r.get("event_type") or doctype.replace("Livestock ", ""),
				},
			)
	return found


def is_livestock_draft(name):
	row = frappe.db.get_value("Stock Entry", name, ["docstatus", "stock_entry_type"], as_dict=True)
	return bool(row) and row.docstatus == 0 and row.stock_entry_type in livestock_stock.livestock_stock_entry_types()


def entry_rows(filters):
	"""The livestock Stock Entries matching `filters` (drafts and posted)."""
	types = livestock_stock.livestock_stock_entry_types()
	entries = frappe.get_all(
		"Stock Entry",
		filters={"docstatus": ["<", 2], **filters, "stock_entry_type": ["in", types]},
		fields=["name", "docstatus", "posting_date", "stock_entry_type", "remarks", "owner", "creation"],
		order_by="posting_date desc, creation desc",
		limit_page_length=500,
	)
	if not entries:
		return []
	names = [e.name for e in entries]
	items = {}
	for d in frappe.get_all(
		"Stock Entry Detail",
		filters={"parent": ["in", names], "parenttype": "Stock Entry"},
		fields=["parent", "item_code", "item_name", "qty", "uom", "s_warehouse"],
		order_by="idx asc",
	):
		items.setdefault(d.parent, []).append(d)
	sources = _sources(names)

	out = []
	for e in entries:
		rows = items.get(e.name, [])
		draft = e.docstatus == 0
		# Only a draft is waiting on the store; a posted entry already took it.
		short = (
			livestock_stock.check_availability(
				[{"item_code": r.item_code, "warehouse": r.s_warehouse, "qty": r.qty} for r in rows]
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
				"remarks": e.remarks,
				"made_by": get_fullname(e.owner),
				"source": sources.get(e.name),
				"items": [
					{
						"item_code": r.item_code,
						"item_name": r.item_name,
						"qty": r.qty,
						"uom": r.uom,
						"warehouse": r.s_warehouse,
					}
					for r in rows
				],
				"can_post": draft and not short,
				"short": livestock_stock.shortage_message(short) if short else None,
			}
		)
	return out


def draft_rows():
	return entry_rows({"docstatus": 0})


def day_counts(from_date, to_date):
	"""{date: {"draft": n, "posted": n}} for the days in range with any entry."""
	types = livestock_stock.livestock_stock_entry_types()
	rows = frappe.db.sql(
		"""SELECT posting_date, docstatus, COUNT(*) AS n FROM `tabStock Entry`
		   WHERE docstatus < 2 AND stock_entry_type IN %(types)s
		     AND posting_date BETWEEN %(from)s AND %(to)s
		   GROUP BY posting_date, docstatus""",
		{"types": types, "from": from_date, "to": to_date},
		as_dict=True,
	)
	days = {}
	for r in rows:
		day = days.setdefault(str(r.posting_date), {"draft": 0, "posted": 0})
		day["draft" if r.docstatus == 0 else "posted"] += r.n
	return days
