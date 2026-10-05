# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Make every submitted disposal agree with the animal it disposed of.

Two faults, found by comparing disposals to their animals on both sites:

1. Disposals and insurance claims from before animals had their own records
   name the ASSET (`DANCAN-129321`), not the Animal. migrate_animals_off_asset
   repointed events and policy rows and left these: on the live site 4
   disposals and 4 claims. They are repointed through Animal.asset_link.
   Disposals naming an asset that no longer exists at all (18 on live, all
   dated 2026-05-22) have nothing to point at and are listed, not guessed.

2. A submitted disposal whose animal is still Active and enabled: the animal
   left, the record says so, and she still counts in her herd and is still
   offered on every screen (4 on kaitet.local). She is retired as the
   disposal would have retired her.

The sale invoice or write-off such a disposal never got is NOT posted here.
Writing historic accounting during a migration is the accountant's call; the
disposals that lack one are written to the Error Log as a list to work from.
"""

import frappe

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES, retire_animal


def execute():
	repoint_to_animals()
	retire_disposed_animals()
	list_what_is_left()


def repoint_to_animals():
	animal_of_asset = dict(frappe.db.sql(
		"SELECT asset_link, name FROM `tabAnimal` WHERE IFNULL(asset_link, '') <> ''"
	))
	for doctype in ("Livestock Disposal", "Livestock Insurance Claim"):
		for name, animal in frappe.db.sql(f"SELECT name, animal FROM `tab{doctype}`"):
			if animal and not frappe.db.exists("Animal", animal) and animal in animal_of_asset:
				frappe.db.set_value(doctype, name, "animal", animal_of_asset[animal], update_modified=False)


def retire_disposed_animals():
	for row in frappe.db.sql(
		"""SELECT d.animal, d.disposal_type
		   FROM `tabLivestock Disposal` d JOIN `tabAnimal` a ON a.name = d.animal
		   WHERE d.docstatus = 1
		     AND (IFNULL(a.disabled, 0) = 0 OR a.status NOT IN %(retired)s)
		   ORDER BY d.disposal_date, d.creation""",
		{"retired": RETIRED_STATUSES},
		as_dict=True,
	):
		retire_animal(row.animal, row.disposal_type)


def list_what_is_left():
	dangling = frappe.db.sql_list(
		"""SELECT d.name FROM `tabLivestock Disposal` d
		   LEFT JOIN `tabAnimal` a ON a.name = d.animal
		   WHERE d.docstatus = 1 AND a.name IS NULL"""
	)
	unposted = frappe.db.sql_list(
		# Only where the asset is still on the books: an asset already Sold or
		# Scrapped was settled some other way, invoice linked here or not.
		"""SELECT d.name FROM `tabLivestock Disposal` d
		   JOIN `tabAnimal` a ON a.name = d.animal
		   JOIN `tabAsset` s ON s.name = a.asset_link
		   WHERE d.docstatus = 1 AND s.docstatus = 1
		     AND s.status NOT IN ('Sold', 'Scrapped', 'Cancelled')
		     AND IFNULL(d.custom_is_backdated, 0) = 0"""
	)
	if dangling or unposted:
		frappe.log_error(
			title="Disposals to reconcile by hand",
			message=(
				"Submitted disposals naming no existing animal:\n  " + ("\n  ".join(dangling) or "none")
				+ "\n\nSubmitted disposals of a capitalised animal with no sale invoice or "
				"write-off, whose asset is still on the books:\n  " + ("\n  ".join(unposted) or "none")
			),
		)
