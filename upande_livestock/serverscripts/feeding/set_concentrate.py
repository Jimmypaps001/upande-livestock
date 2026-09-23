# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Create a concentrate, or revise the recipe of one that exists."""

import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.feeding._concentrate import set_concentrate as _set


@frappe.whitelist()
def set_concentrate(payload):
	"""Name it, give it ingredients, and say what they make.

	Guards BOM because that is what it writes. Naming a concentrate the farm
	does not have yet creates it — both the recipe and the product it is a
	recipe for, which ERPNext requires and which is not a decision to put in
	front of someone mid-recipe. See `_concentrate`.
	"""

	def go():
		guard("BOM")
		d = as_dict(payload)
		res = _set(
			d.get("name"),
			d.get("lines") or [],
			d.get("base_qty"),
			farm=d.get("farm"),
		)
		res["ok"] = True
		return res

	return run(go, "livestock set_concentrate failed")
