# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Describe the feed items with book values, so the Ration Editor has numbers to show.

Creates a Livestock Feed record for each Item in the Feed Item Group whose name
matches a common East African ingredient, with `nutrient_source = "Book value"`.
The figures are typical published values (Feedipedia / NRC ranges, rounded) —
good enough to design and demonstrate with, and to be replaced by a lab
analysis or the supplier's label. A record already marked Lab analysis or
Supplier label is left alone.

Made feeds (a concentrate or ration that has a BOM) get no record: their
nutrition is computed from their recipe. Items that match nothing are listed,
not guessed at.

    bench --site mutara.local execute upande_livestock.demo.seed_livestock_feeds.run

Development and training sites only; refuses a site that is not a `.local` one
unless `force=True`. Never run on live without approval.
"""

import re

import frappe

# (pattern on the lower-cased item name, category, values). Percent fields are
# % of dry matter except dry_matter_pct, which is as fed. ME is MJ per kg DM.
BOOK = [
	(r"maize germ", "Energy (grain / by-product)",
	 dict(dry_matter_pct=90, crude_protein_pct=14, carbohydrate_pct=42, fibre_ndf_pct=28, fat_pct=9,
	      energy_me_mj_per_kg=13.5, calcium_pct=0.05, phosphorus_pct=1.0)),
	(r"wheat bran|\bbran\b", "Energy (grain / by-product)",
	 dict(dry_matter_pct=89, crude_protein_pct=16, carbohydrate_pct=25, fibre_ndf_pct=42, fat_pct=4,
	      energy_me_mj_per_kg=11.5, calcium_pct=0.12, phosphorus_pct=1.1)),
	(r"cotton\s*seed\s*cake|cottonseed cake", "Protein",
	 dict(dry_matter_pct=91, crude_protein_pct=30, carbohydrate_pct=14, fibre_ndf_pct=38, fat_pct=7,
	      energy_me_mj_per_kg=10.5, calcium_pct=0.2, phosphorus_pct=1.0)),
	(r"sunflower (seed )?cake", "Protein",
	 dict(dry_matter_pct=91, crude_protein_pct=32, carbohydrate_pct=12, fibre_ndf_pct=40, fat_pct=8,
	      energy_me_mj_per_kg=10.0, calcium_pct=0.4, phosphorus_pct=1.0)),
	(r"silage", "Forage",
	 dict(dry_matter_pct=30, crude_protein_pct=8, carbohydrate_pct=33, fibre_ndf_pct=45, fat_pct=3,
	      energy_me_mj_per_kg=10.5, calcium_pct=0.25, phosphorus_pct=0.22)),
	(r"rhodes|\bhay\b", "Forage",
	 dict(dry_matter_pct=90, crude_protein_pct=8, carbohydrate_pct=8, fibre_ndf_pct=72, fat_pct=2,
	      energy_me_mj_per_kg=8.0, calcium_pct=0.35, phosphorus_pct=0.2)),
	(r"molasses", "Energy (grain / by-product)",
	 dict(dry_matter_pct=75, crude_protein_pct=5, carbohydrate_pct=65, fibre_ndf_pct=0, fat_pct=0.1,
	      energy_me_mj_per_kg=12.0, calcium_pct=0.9, phosphorus_pct=0.1)),
	(r"limestone", "Mineral & vitamin",
	 dict(dry_matter_pct=99, calcium_pct=36, phosphorus_pct=0)),
	(r"\bdcp\b|dicalcium", "Mineral & vitamin",
	 dict(dry_matter_pct=97, calcium_pct=22, phosphorus_pct=18)),
	(r"\bsalt\b", "Mineral & vitamin",
	 dict(dry_matter_pct=99, calcium_pct=0, phosphorus_pct=0)),
	(r"mineral|lick", "Mineral & vitamin",
	 dict(dry_matter_pct=95, calcium_pct=12, phosphorus_pct=5)),
	# A bought-in compound feed has no recipe here to compute from, so it needs a
	# figure. These are generic beef-finisher / small-stock pellet values, a
	# stand-in until the supplier's label is typed in.
	(r"beef meal|pellets?", "Energy (grain / by-product)",
	 dict(dry_matter_pct=89, crude_protein_pct=16, carbohydrate_pct=38, fibre_ndf_pct=28, fat_pct=3.5,
	      energy_me_mj_per_kg=11.5, calcium_pct=0.8, phosphorus_pct=0.5)),
]

NOTE = "Typical book value, rounded. Replace with a lab analysis or the supplier's label."


def _match(item_name):
	name = (item_name or "").lower()
	for pattern, category, values in BOOK:
		if re.search(pattern, name):
			return category, values
	return None


def run(force=False):
	site = frappe.local.site
	if not force and not site.endswith(".local"):
		frappe.throw(f"{site} is not a .local site. Pass force=True only with approval.")

	from upande_livestock.serverscripts.feeding.feed_in_store import feed_item_group

	group = feed_item_group()
	items = frappe.get_all(
		"Item", filters={"item_group": group, "disabled": 0},
		fields=["name", "item_name"], order_by="item_name asc",
	)
	made, created, updated, kept, unmatched = [], [], [], [], []
	for it in items:
		if frappe.db.get_value("Item", it.name, "default_bom") or frappe.db.exists(
			"BOM", {"item": it.name, "docstatus": 1, "is_active": 1}
		):
			made.append(it.name)
			continue
		hit = _match(it.item_name or it.name)
		if not hit:
			unmatched.append(it.name)
			continue
		category, values = hit
		existing = frappe.db.get_value("Livestock Feed", it.name, "nutrient_source")
		if existing in ("Lab analysis", "Supplier label"):
			kept.append(it.name)
			continue
		doc = (
			frappe.get_doc("Livestock Feed", it.name)
			if frappe.db.exists("Livestock Feed", it.name)
			else frappe.new_doc("Livestock Feed")
		)
		doc.item = it.name
		doc.category = category
		doc.nutrient_source = "Book value"
		doc.notes = NOTE
		for field in ("crude_protein_pct", "carbohydrate_pct", "fibre_ndf_pct", "fat_pct",
		              "energy_me_mj_per_kg", "calcium_pct", "phosphorus_pct"):
			doc.set(field, 0)
		for field, value in values.items():
			doc.set(field, value)
		(updated if doc.get("creation") else created).append(it.name)
		doc.save(ignore_permissions=True)
	frappe.db.commit()

	print(f"Livestock Feed records on {site}")
	print(f"  created   : {len(created)}  {created}")
	print(f"  refreshed : {len(updated)}  {updated}")
	print(f"  kept (lab / supplier figures): {kept}")
	print(f"  made feeds (computed from their recipe, no record): {len(made)}")
	print(f"  unmatched : {unmatched}")
	return {"created": created, "refreshed": updated, "kept": kept, "made": made, "unmatched": unmatched}
