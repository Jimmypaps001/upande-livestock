# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The livestock stock issues still in draft, and what each is waiting for.

An event recorded today when the store could not cover it saves its issue as a
draft (common/stock). These are those drafts: what was used, by which record,
and whether the store can cover it now.
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


def draft_rows():
	types = livestock_stock.livestock_stock_entry_types()
	entries = frappe.get_all(
		"Stock Entry",
		filters={"docstatus": 0, "stock_entry_type": ["in", types]},
		fields=["name", "posting_date", "stock_entry_type", "remarks", "owner", "creation"],
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
		short = livestock_stock.check_availability(
			[{"item_code": r.item_code, "warehouse": r.s_warehouse, "qty": r.qty} for r in rows]
		)
		out.append(
			{
				"name": e.name,
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
				"can_post": not short,
				"short": livestock_stock.shortage_message(short) if short else None,
			}
		)
	return out
