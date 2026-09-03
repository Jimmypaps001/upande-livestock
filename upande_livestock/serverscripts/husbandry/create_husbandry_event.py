"""Record a routine husbandry event — vaccination, deworming, hoof trimming —
against one animal or a whole herd, issuing any drugs it consumes."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event
from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.husbandry._shared import HUSBANDRY_TYPES, _clean_drug_rows, _husbandry_targets, _type_consumes_drugs


@frappe.whitelist()
def create_husbandry_event(payload):
	"""Record a Vaccination / Deworming / Dehorning / Hoof Trimming event.

	For the two drug-consuming types the `drugs` rows become Livestock Drug Issue
	child rows, and LivestockEvent.on_submit posts them as one Material Issue out of
	the drug store. A drug row with no item or a non-positive qty is dropped rather
	than rejected — a half-filled line should not cost the user the whole event.

	The event records even when the issue cannot post; see
	livestock_stock.try_issue_items for why that is the deliberate choice.
	"""

	def go():
		guard("Livestock Event")
		d = as_dict(payload)
		event_type = d.get("event_type")
		if event_type not in HUSBANDRY_TYPES:
			frappe.throw(
				_("{0} is not a husbandry event type. Expected one of: {1}.").format(
					event_type or _("(none)"), ", ".join(HUSBANDRY_TYPES)
				)
			)

		animals = _husbandry_targets(d)
		consumes = _type_consumes_drugs(event_type)
		default_wh = d.get("source_warehouse") or livestock_stock.drug_warehouse()
		drugs = _clean_drug_rows(d.get("drugs"), default_wh) if consumes else []

		# One Material Issue for the whole round, not one per animal. Dosing is
		# entered per animal — 2 ml a cow across 119 cows — so the store sees a
		# single line of 238 ml, which is both what left the shelf and what the
		# storekeeper can reconcile. The events are then stamped with that entry,
		# and LivestockEvent.post_stock_issue's `self.stock_entry` guard stops each
		# one posting again.
		stock_entry = None
		if drugs:
			rows = [
				{
					"item_code": drug["item_code"],
					"qty": drug["qty"] * len(animals),
					"warehouse": drug["source_warehouse"],
					"batch_no": drug.get("batch_no"),
					"uom": drug.get("uom"),
				}
				for drug in drugs
			]
			stock_entry = livestock_stock.issue_items(
				rows,
				remarks="Livestock {0} - {1} animal(s)".format(event_type, len(animals)),
				posting_date=d.get("event_date"),
				employee=d.get("operator"),
				# So the ledger says "Deworming", not "Material Issue".
				what=event_type,
			)

		created = []
		for animal in animals:
			doc = new_livestock_event(dict(d, animal=animal), event_type)
			for drug in drugs:
				doc.append("drug_issues", dict(drug, stock_entry_ref=stock_entry))
			if stock_entry:
				doc.stock_entry = stock_entry
			doc.insert()
			doc.submit()
			created.append(doc.name)

		return {
			"ok": True,
			"name": created[0] if created else "",
			"names": created,
			"animals": len(created),
			"event_type": event_type,
			"stock_entry": stock_entry or "",
			"drugs_issued": len(drugs),
			"qty_per_animal": sum(drug["qty"] for drug in drugs),
		}

	return run(go, "livestock create_husbandry_event failed")
