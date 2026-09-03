"""The husbandry vocabulary, shared by this package's four endpoints.

Which routine event types exist, which of them draw drugs from the store, and
how a whole-herd event fans out to its animals. Kept together because they are
one vocabulary: a type added to HUSBANDRY_TYPES without a matching decision in
DRUG_CONSUMING_TYPES is the bug this grouping makes obvious.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common.choices import (
	ANIMAL_FIELDS,
	RETIRED_STATUSES,
	animal_label,
	herd_label_map,
)


HUSBANDRY_TYPES = ("Vaccination", "Deworming", "Dehorning", "Hoof Trimming")


DRUG_CONSUMING_TYPES = ("Vaccination", "Deworming")


def _type_consumes_drugs(event_type):
	"""Read off Livestock Event Type, so the farm can flag a new drug-consuming
	type without a deploy. DRUG_CONSUMING_TYPES is the fallback for a site whose
	event types predate the flag."""
	flagged = frappe.db.get_value("Livestock Event Type", event_type, "consumes_drugs")
	if flagged is None:
		return event_type in DRUG_CONSUMING_TYPES
	return bool(flagged)


def _animals_in_herd(herd):
	"""Animals in a herd that may still receive an event.

	Same rule as active_animals — retired status or `disabled` excludes an
	animal. `Herds.number_of_animals` is NOT that count: it counts every animal
	whose current_herd points here regardless of status, so dosing off it would
	issue drugs for cows that are dead or sold.
	"""
	return frappe.get_all(
		"Animal",
		filters=[
			["current_herd", "=", herd],
			["status", "not in", RETIRED_STATUSES],
			["disabled", "=", 0],
		],
		fields=ANIMAL_FIELDS,
		order_by="tag_number asc",
		limit=5000,
	)


def _husbandry_targets(d):
	"""The animals this event applies to: one, a chosen set, or a whole herd.

	Deworming a herd is one operation to the person doing it and one issue out of
	the store, but it is still a clinical fact about each cow — withdrawal dates
	and next-due dates are per animal. So the round fans out into one event per
	animal, and only the stock side is batched.
	"""
	animals = [a for a in (d.get("animals") or []) if a]
	if not animals and d.get("animal"):
		animals = [d["animal"]]
	if not animals and d.get("herd"):
		animals = [a.name for a in _animals_in_herd(d["herd"])]
		if not animals:
			frappe.throw(_("Herd {0} has no active animals.").format(d["herd"]))
	if not animals:
		frappe.throw(_("Select an animal, a set of animals, or a herd."))
	return animals


def _clean_drug_rows(drugs, default_wh):
	"""Drop half-filled drug lines; quantities here are PER ANIMAL.

	A blank line should not cost the user the whole event, so an incomplete row is
	dropped rather than rejected.
	"""
	rows = []
	for drug in drugs or []:
		if not drug.get("item_code") or flt(drug.get("qty")) <= 0:
			continue
		rows.append(
			{
				"item_code": drug["item_code"],
				"qty": flt(drug["qty"]),
				"source_warehouse": drug.get("source_warehouse") or default_wh,
				"batch_no": drug.get("batch_no"),
				"dosage": drug.get("dosage"),
				"uom": drug.get("uom"),
				"withdrawal_days": int(flt(drug.get("withdrawal_days"))) or None,
				"next_due_date": drug.get("next_due_date") or None,
			}
		)
	return rows
