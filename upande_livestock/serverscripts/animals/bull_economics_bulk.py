# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""bull_economics_bulk: split out of animals.bull_economics; that module still re-exports it, so the old dotted path resolves."""

from frappe.utils import flt
import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run


@frappe.whitelist()
def bull_economics_bulk(payload=None):
	"""{bulls: {id: economics}} for the named bulls, or every bull still on the farm.

	One cache across the lot: a herd's feed days are read once however many of
	its bulls are asked about. No weight series -- the list needs the figures.
	"""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.animals.bull_economics import RETIRED, _Cache, _fields, economics, purpose


	def go():
		guard_read("Animal")
		names = as_dict(payload).get("animals")
		filters = {"sex": "Male"}
		if names:
			filters["name"] = ["in", list(names)]
		rows = frappe.get_all("Animal", filters=filters, fields=_fields(), limit_page_length=0)
		if not names:
			rows = [r for r in rows if not r.disabled and (r.status or "") not in RETIRED]
		price = flt(frappe.db.get_single_value("Livestock Settings", "bull_price_per_kg"))
		cache, why = _Cache(), purpose()
		return {"ok": True, "purpose": why,
		        "bulls": {r.name: economics(r, cache, price, why, with_series=False) for r in rows}}

	return run(go, "livestock bull_economics_bulk failed")
