# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the Shoats screens offer: species, class labels, event types, causes, drugs in the Drug Store, herds."""

import frappe
from frappe.utils import flt, today

from upande_livestock.serverscripts.common import shoats
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run

CAUSES = ["Disease", "Predation", "Theft", "Accident", "Cold or Exposure", "Poisoning", "Old Age", "Unknown", "Other"]

# direction: in (adds head), out (takes head), set (head count), move (weaning), none (mating)
EVENT_TYPES = [
	{"name": "Head Count", "direction": "set", "needs": ["females", "males", "young", "others"]},
	{"name": "Birth", "direction": "in", "needs": ["young", "born_dead"], "optional": ["mating"]},
	{"name": "Death", "direction": "out", "needs": ["cause"]},
	{"name": "Purchase", "direction": "in", "needs": [], "optional": ["amount", "reason"]},
	{"name": "Sale", "direction": "out", "needs": [], "optional": ["amount", "reason"]},
	{"name": "Slaughter", "direction": "out", "needs": [], "optional": ["amount", "reason"]},
	{"name": "Transfer In", "direction": "in", "needs": ["other_herd"], "optional": ["paddock"]},
	{"name": "Transfer Out", "direction": "out", "needs": ["other_herd"], "optional": ["paddock"]},
	{"name": "Weaning", "direction": "move", "needs": ["females", "males", "others"], "optional": ["other_herd", "mating"]},
	{"name": "Mating", "direction": "none", "needs": ["females", "males", "mating_start"], "optional": ["mating_end"]},
]


@frappe.whitelist()
def shoat_options():
	def go():
		guard_read("Herds")
		from upande_livestock.upande_livestock.doctype.herd_treatment.herd_treatment import drug_store

		store = drug_store()
		drugs = []
		if store:
			rows = frappe.db.sql(
				"""SELECT b.item_code, i.item_name, i.stock_uom, b.actual_qty FROM `tabBin` b
				   JOIN `tabItem` i ON i.name = b.item_code
				   WHERE b.warehouse = %s AND b.actual_qty > 0 AND i.disabled = 0 ORDER BY i.item_name""",
				(store,), as_dict=True)
			drugs = [{"item_code": r.item_code, "item_name": r.item_name, "uom": r.stock_uom,
			          "qty": flt(r.actual_qty)} for r in rows]
		herds = [{"name": h.name, "label": h.herd_name or h.name, "species": h.species or "Sheep",
		          "head": int(h.number_of_animals or 0)}
		         for h in frappe.get_all("Herds", filters={"counting": "By number"},
		                                 fields=["name", "herd_name", "species", "number_of_animals"],
		                                 order_by="species asc, name asc")]
		return {
			"ok": True, "today": today(), "operator": current_employee(),
			"species": list(shoats.SPECIES),
			"classes": {s: [{"key": k, "label": shoats.label(s, k)} for k in shoats.CLASSES] for s in shoats.SPECIES},
			"event_types": EVENT_TYPES, "death_causes": CAUSES,
			"treatment_types": list(shoats.TREATMENT_TYPES),
			"sample_classes": [{"key": "All", "label": "Whole herd"},
			                   *[{"key": k, "label_sheep": shoats.label("Sheep", k), "label_goat": shoats.label("Goat", k)}
			                     for k in shoats.CLASSES]],
			"drug_store": store, "drugs": drugs, "herds": herds,
			"gestation_days": shoats.gestation_days(),
		}

	return run(go, "livestock shoat_options failed")
