# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Rewrite recipe lines so no concentrate is left in them.

For a farm that has turned Pre-manufacture Concentrate off: a ration that still
names a made concentrate is rewritten from that concentrate's newest active BOM,
scaled to the kilos the line carried, and merged with any raw line of the same
feed. The server does the arithmetic and the decision of what a concentrate is
(`concentrate_items`); the page only shows the answer and saves it as usual.

Read-guarded on BOM, like `concentrates.py`: it writes nothing.
"""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.feeding._concentrate import concentrate_items
from upande_livestock.serverscripts.feeding._doses import dose_uom_of
from upande_livestock.serverscripts.feeding.feed_nutrition import DbSource

MAX_DEPTH = 6


def expand_lines(lines, source=None, concentrates=None):
	"""([{item_code, qty[, dose_uom]}, ...], [item_code expanded]) with
	concentrates replaced.

	A per-head dose in the ration is carried through untouched. A dose inside
	a concentrate's recipe is stated per batch, so it becomes a per-head dose
	at the share of the batch the line carried: 50 g in a 1000 kg batch, for a
	2 kg line, is 0.1 g a head — still grams, never added to the kilos.
	"""
	source = source or DbSource()
	concentrates = concentrate_items() if concentrates is None else concentrates
	merged, expanded = {}, []

	def add(item, qty, depth=0, dose=None):
		recipe = (
			source.recipe(item) if not dose and item in concentrates and depth < MAX_DEPTH else None
		)
		if not recipe:
			merged[(item, dose)] = merged.get((item, dose), 0.0) + qty
			return
		if item not in expanded:
			expanded.append(item)
		base = recipe[0] or sum(q for _i, q in recipe[1]) or 1.0
		for sub, sub_qty in recipe[1]:
			add(sub, qty * sub_qty / base, depth + 1)
		for sub, sub_qty, uom in recipe[3] if len(recipe) > 3 else []:
			add(sub, qty * sub_qty / base, depth + 1, dose=uom)

	order = []
	for row in lines or []:
		code, qty = row.get("item_code"), flt(row.get("qty"))
		if code and qty > 0:
			order.append((code, qty, dose_uom_of(row)))
	for code, qty, dose in order:
		add(code, qty, dose=dose)
	out = []
	for (item, dose), v in merged.items():
		line = {"item_code": item, "qty": round(v, 4)}
		if dose:
			line["dose_uom"] = dose
		out.append(line)
	return out, expanded


@frappe.whitelist()
def expand_concentrates(payload=None, lines=None):
	def go():
		guard_read("BOM")
		body = as_dict(payload)
		raw = lines if lines is not None else body.get("lines") or []
		if isinstance(raw, str):
			raw = frappe.parse_json(raw)
		out, expanded = expand_lines(raw)
		names = {i: frappe.db.get_value("Item", i, "item_name") or i for i in [r["item_code"] for r in out]}
		for r in out:
			r["item_name"] = names[r["item_code"]]
		return {"ok": True, "lines": out, "expanded": expanded}

	return run(go, "livestock expand_concentrates failed")
