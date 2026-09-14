# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Give a herd its standing ration, or revise the one it has."""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.feeding._standing_ration import set_standing_ration


@frappe.whitelist()
def set_herd_ration(payload):
	"""Set what this herd is fed, per head, per day.

	Guards BOM because that is what it writes. The herd document is only
	repointed — the recipe is the new record, and it is the recipe that decides
	what leaves the store tomorrow morning.

	The reply says what the change actually is, line by line, because a ration
	is edited by someone who wants to know they changed what they meant to
	change. "Saved" is not an answer when the number moves a tonne of silage a
	week.
	"""

	def go():
		guard("BOM")
		d = as_dict(payload)
		herd = (d.get("herd") or "").strip()
		if not herd:
			frappe.throw(_("Select the herd."))
		if not frappe.db.exists("Herds", herd):
			frappe.throw(_("{0} is not a herd on this farm.").format(herd))

		before = _lines_of(frappe.db.get_value("Herds", herd, "bom"))
		result = set_standing_ration(
			herd, d.get("lines") or [],
			ration_item=(d.get("ration_item") or "").strip() or None,
		)
		after = _lines_of(result["bom"])

		heads = flt(frappe.db.get_value("Herds", herd, "number_of_animals"))
		return {
			"ok": True,
			"herd": herd,
			**result,
			"heads": heads,
			"day_kg": flt(result["per_head_kg"]) * heads,
			"differences": _differences(before, after),
		}

	return run(go, "livestock set_herd_ration failed")


def _lines_of(bom_name):
	if not bom_name:
		return {}
	return {
		r.item_code: flt(r.qty)
		for r in frappe.get_all("BOM Item", filters={"parent": bom_name},
		                        fields=["item_code", "qty"])
	}


def _differences(before, after):
	"""What moved, in the farm's terms: added, dropped, or changed by how much.

	Reported against the previous ration rather than against the request, so a
	revision that turns out to change nothing says so.
	"""
	out = []
	for item in sorted(set(before) | set(after)):
		was, now = flt(before.get(item)), flt(after.get(item))
		if abs(was - now) < 0.0005:
			continue
		name = frappe.db.get_value("Item", item, "item_name") or item
		if not was:
			out.append({"item_code": item, "item_name": name, "was": 0.0, "now": now,
			            "what": "added"})
		elif not now:
			out.append({"item_code": item, "item_name": name, "was": was, "now": 0.0,
			            "what": "dropped"})
		else:
			out.append({"item_code": item, "item_name": name, "was": was, "now": now,
			            "what": "raised" if now > was else "lowered"})
	return out
