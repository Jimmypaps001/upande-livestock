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
)


HUSBANDRY_TYPES = ("Vaccination", "Deworming", "Dehorning", "Hoof Trimming")


DRUG_CONSUMING_TYPES = ("Vaccination", "Deworming")


def _type_consumes_drugs(event_type):
	"""Whether this event type consumes anything, per the farm's mapping.

	It used to read a `consumes_drugs` checkbox on Livestock Event Type, so the
	farm could flag a new drug-consuming type without a deploy. What an event may
	consume is a list the farm writes now; the mapping is asked first. The
	checkbox stays as the fallback for a site running this code before its
	migrate, and DRUG_CONSUMING_TYPES for a site whose event types predate the
	flag.
	"""
	from upande_livestock.serverscripts.common import event_items

	if event_items.groups_for_event(event_type):
		return True
	# The mapping, once written, is the whole answer; see event_items.has_mapping.
	if event_items.has_mapping():
		return False
	flagged = frappe.db.get_value("Livestock Event Type", event_type, "consumes_drugs")
	if flagged is None:
		return event_type in DRUG_CONSUMING_TYPES
	return bool(flagged)


def husbandry_drug_items():
	"""Items any husbandry event may consume, one choice per item.

	The husbandry screen serves every routine type from one payload, so this is
	the union of what the farm mapped to each of them. Two types mapped to the
	same group yield the same items, which are listed once.
	"""
	from upande_livestock.serverscripts.common.event_items import items_for_event

	seen = {}
	for event_type in HUSBANDRY_TYPES:
		for item in items_for_event(event_type):
			seen.setdefault(item["value"], item)
	return sorted(seen.values(), key=lambda i: (i["item_name"] or "").lower())


def husbandry_items_mapped():
	"""Whether the farm mapped item groups to ANY husbandry event type.

	`husbandry_drug_items()` is [] both when nothing is mapped and when what is
	mapped is out of stock; the screen words those differently, so it is told.
	"""
	from upande_livestock.serverscripts.common.event_items import consumes_items

	return any(consumes_items(t) for t in HUSBANDRY_TYPES)


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


def _refuse_foreign_items(event_type, rows):
	"""Refuse a drug row whose item is not in a group mapped to THIS event type.

	The options payload carries the union of every husbandry type's items, so the
	picker can offer a dewormer on a Vaccination. Naming the line is better than
	dropping it: the farm sees which one it cannot use. A site with no mapping
	for the type (running before its migrate) has nothing to check against and
	keeps the old behaviour.
	"""
	from upande_livestock.serverscripts.common import event_items

	groups = event_items.groups_for_event(event_type)
	if not groups:
		return
	for row in rows:
		group = frappe.db.get_value("Item", row["item_code"], "item_group")
		if group not in groups:
			frappe.throw(
				_("{0} is not an item a {1} may use. Its group, {2}, is not mapped to {1}.").format(
					row["item_code"], event_type, group or _("(none)")
				)
			)


def append_items(doc, d):
	"""Put what an event used onto its drug_issues, if the payload names any.

	Shared by every creator that is not the husbandry endpoint, so that an event
	type the farm mapped items to can record them without each endpoint growing
	its own copy. Rows are cleaned (half-filled ones dropped), then checked
	against the mapping for THIS type, then appended. The default warehouse is
	None on purpose: a row whose store the picker could not place falls back
	inside `post_stock_issue`, not here.
	"""
	rows = _clean_drug_rows(d.get("items"), None)
	_refuse_foreign_items(doc.event_type, rows)
	for row in rows:
		doc.append("drug_issues", row)
