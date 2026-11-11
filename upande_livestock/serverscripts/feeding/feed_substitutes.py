# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which feeds can stand in for one another at the mixer, and how much of one.

Mutara's wet forage is whatever the pits and fields have that week: maize
silage, chopped green maize, Napier, sorghum silage. The ration sheet names
one; the mixer gets another. `Livestock Feed.substitute_group` says which
feeds are interchangeable ("Wet forage"), and a swap keeps the herd's DRY
MATTER the same: 10 kg of silage at 30% DM is 3 kg of DM, which is 15 kg of
Napier at 20% DM. Swapping kilo for kilo would quietly starve the herd on the
wetter feed and overfeed it on the drier.

A swap is a change to one day's mix, not to the herd's ration. The Feeding
page posts it through `manual_feed` — the tuned-BOM path that exists for
exactly that — and `Herds.bom` is never touched.

The kilos are worked out here (`dm_equivalent_kg`), and the page shows the
answer; it does not do the arithmetic.

Read-guarded on Livestock Feed.
"""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run


def dm_equivalent_kg(qty, dm_from, dm_to):
	"""Kilos of the new feed carrying the dry matter `qty` kilos of the old one did.

	None when either dry matter is unknown or zero: a swap that cannot be
	balanced on dry matter must not be offered as if it were.
	"""
	dm_from, dm_to = flt(dm_from), flt(dm_to)
	if dm_from <= 0 or dm_to <= 0:
		return None
	return flt(qty) * dm_from / dm_to


def substitutes_for(item_code, feeds):
	"""The feeds in `item_code`'s substitute group, other than itself. Pure.

	`feeds` is {item_code: {"substitute_group", "dry_matter_pct", "feed_name",
	"disabled"}}. Each answer carries `factor`: kilos of it per kilo of
	`item_code`, so the page multiplies rather than divides. A feed with no
	dry matter on either side is listed with `factor` None and the reason, so
	the operator sees it exists and why it cannot be swapped.
	"""
	own = feeds.get(item_code) or {}
	group = (own.get("substitute_group") or "").strip()
	if not group:
		return []
	out = []
	for code, rec in feeds.items():
		if code == item_code or rec.get("disabled"):
			continue
		if (rec.get("substitute_group") or "").strip().lower() != group.lower():
			continue
		factor = dm_equivalent_kg(1.0, own.get("dry_matter_pct"), rec.get("dry_matter_pct"))
		out.append(
			{
				"item_code": code,
				"item_name": rec.get("feed_name") or code,
				"group": group,
				"dry_matter_pct": flt(rec.get("dry_matter_pct")),
				"factor": round(factor, 6) if factor else None,
				"reason": None if factor else "no dry matter recorded",
			}
		)
	out.sort(key=lambda r: (r["factor"] is None, r["item_name"].lower()))
	return out


def _feeds():
	rows = frappe.get_all(
		"Livestock Feed",
		filters=[["substitute_group", "is", "set"]],
		fields=["name", "feed_name", "substitute_group", "dry_matter_pct", "disabled"],
	)
	return {r.name: r for r in rows}


@frappe.whitelist()
def feed_substitutes(items=None, payload=None):
	"""{item_code: [substitute, ...]} for each item asked about.

	Items with no group, or alone in theirs, are left out, so the page offers
	a swap only where one exists. Each substitute says what the store holds,
	because swapping to a feed the store does not have is no help at 6 am.
	"""

	def go():
		guard_read("Livestock Feed")
		asked = items if items is not None else as_dict(payload).get("items")
		if isinstance(asked, str):
			asked = frappe.parse_json(asked)
		feeds = _feeds()
		out = {}
		for code in asked or []:
			subs = substitutes_for(code, feeds)
			if subs:
				out[code] = subs
		codes = sorted({s["item_code"] for subs in out.values() for s in subs})
		if codes:
			info = {
				r.name: r
				for r in frappe.get_all(
					"Item", filters={"name": ["in", codes]}, fields=["name", "stock_uom"]
				)
			}
			on_hand = dict(
				frappe.db.sql(
					"""SELECT item_code, IFNULL(SUM(actual_qty), 0) FROM `tabBin`
					   WHERE item_code IN %(codes)s GROUP BY item_code""",
					{"codes": tuple(codes)},
				)
			)
			for subs in out.values():
				for s in subs:
					s["stock_uom"] = (info.get(s["item_code"]) or {}).get("stock_uom")
					s["on_hand"] = flt(on_hand.get(s["item_code"]))
		return {"ok": True, "substitutes": out}

	return run(go, "livestock feed_substitutes failed")
