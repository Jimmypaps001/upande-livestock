"""Migrate livestock from the Asset model to the standalone Animal doctype.

For every Asset flagged `custom_is_livestock`, create a matching `Animal`
record (linked back via `asset_link` for capitalisation/insurance), then
repoint every `Livestock Event` and `Livestock Insurance Policy Animal` from the
Asset name to the new Animal name, and recompute `Herds.number_of_animals`
from Animal membership.

Idempotent: keyed on `Animal.asset_link`, so re-running skips already-migrated
animals and leaves already-repointed events alone. Safe on fresh installs
(no livestock Assets / no custom column -> no-op).
"""

import frappe

from upande_livestock.serverscripts.common.animal import live_herd_count


def execute():
	# Fresh install or already-removed Asset custom fields -> nothing to migrate.
	if not frappe.db.has_column("Asset", "custom_is_livestock"):
		print("migrate_animals_off_asset: Asset.custom_is_livestock absent; skipping")
		return

	herds = set(frappe.get_all("Herds", pluck="name"))
	breeds = set(frappe.get_all("Breed", pluck="name"))
	default_company = (
		frappe.db.get_single_value("Global Defaults", "default_company")
		or ((frappe.get_all("Company", limit=1, pluck="name") or [None])[0])
	)

	# asset name -> animal name (seed with anything already migrated)
	asset_to_animal = {
		a.asset_link: a.name
		for a in frappe.get_all(
			"Animal", filters={"asset_link": ["is", "set"]}, fields=["name", "asset_link"]
		)
	}
	used_tags = set(frappe.get_all("Animal", pluck="tag_number"))

	assets = frappe.get_all(
		"Asset",
		filters={"custom_is_livestock": 1},
		fields=[
			"name",
			"asset_name",
			"custom_animal_id",
			"custom_breed",
			"custom_sex",
			"custom_birth_date",
			"custom_current_herd",
			"company",
		],
	)

	created = 0
	for a in assets:
		if a.name in asset_to_animal:
			continue
		tag = (a.custom_animal_id or "").strip() or (a.asset_name or "").strip() or a.name
		base, i = tag, 1
		while tag in used_tags:
			i += 1
			tag = f"{base}-{i}"
		used_tags.add(tag)

		doc = frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": tag,
				"burn_name": (a.asset_name or "").strip() or tag,
				"sex": a.custom_sex if a.custom_sex in ("Female", "Male") else "Female",
				"breed": a.custom_breed if a.custom_breed in breeds else None,
				"company": a.company or default_company,
				"current_herd": a.custom_current_herd if a.custom_current_herd in herds else None,
				"date_of_birth": a.custom_birth_date,
				"origin": "Born on Farm",
				"status": "Active",
				"is_capitalised": 1,
				"asset_link": a.name,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		asset_to_animal[a.name] = doc.name
		created += 1
	frappe.db.commit()

	# Repoint Livestock Event.animal (Asset name -> Animal name). db.set_value bypasses
	# submit-immutability, which is what we want for a historical repoint.
	repointed, unmapped = 0, set()
	for ev in frappe.get_all("Livestock Event", fields=["name", "animal"]):
		if not ev.animal:
			continue
		if ev.animal in asset_to_animal:
			frappe.db.set_value(
				"Livestock Event", ev.name, "animal", asset_to_animal[ev.animal], update_modified=False
			)
			repointed += 1
		elif not frappe.db.exists("Animal", ev.animal):
			unmapped.add(ev.animal)
	frappe.db.commit()

	# Repoint insurance child rows
	ins = 0
	for r in frappe.get_all("Livestock Insurance Policy Animal", fields=["name", "animal"]):
		if r.animal in asset_to_animal:
			frappe.db.set_value(
				"Livestock Insurance Policy Animal",
				r.name,
				"animal",
				asset_to_animal[r.animal],
				update_modified=False,
			)
			ins += 1
	frappe.db.commit()

	# Recompute herd headcounts from Animal membership
	for h in herds:
		cnt = live_herd_count(h)
		frappe.db.set_value("Herds", h, "number_of_animals", cnt, update_modified=False)
	frappe.db.commit()

	print(
		f"migrate_animals_off_asset: created {created} animals "
		f"({len(asset_to_animal)} total mapped); repointed {repointed} events, "
		f"{ins} insurance rows; {len(unmapped)} unmapped event animals: {sorted(unmapped)[:10]}"
	)
