# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Build the lactating concentrate's own recipe, from the August 2026 sheet.

THE GAP THIS CLOSES. Five of the six concentrates on the formulation sheet are
manufacturable here: Weaner Meal, Weaners/Yearlings, Dry Cows Meal and Calves
Meal each have a BOM, and a Work Order can mix them. The sixth — the one the
two lactating herds eat, and by far the largest run at about 6.3 tonnes a week —
had no BOM at all, and was listed on Livestock Settings as a *bought-in*
concentrate. So the system treated the farm's own mix as a purchase, and
`manufacture_concentrate` refused it for want of a recipe.

The sheet is unambiguous that it is mixed here: it gives a full 1000 kg
formulation costed at 40.21/kg. This builds that recipe and takes the item off
the bought-in list.

ONE BATCH IS 1000 KG, matching the sheet and the four existing concentrate
BOMs. A week's requirement is then a Work Order for however many batches cover
it — `manufacture_concentrate` already scales a partial batch.

NOTHING IS INVENTED. Every ingredient resolves to an item already on the site,
by explicit code, pinned below and shared with build_feed_rations. A name that
does not resolve is reported and the build is skipped.

    bench --site <site> execute upande_livestock.demo.build_concentrates.run
    bench --site <site> execute upande_livestock.demo.build_concentrates.apply_now

`apply_now` exists because `bench execute` only imports the module on the
no-argument path; passing --args or --kwargs makes it eval a dotted name it
never imported, and the call dies with a bare NameError naming the app.
"""

import frappe
from frappe.utils import flt

BATCH_KG = 1000.0
RECIPE_UOM = "Kilogram"

# Same pinned codes as build_feed_rations. "High Phosphorous Maziwa" on the
# sheet is 4040010052 "High Phosphorous Mineral (Maziwa)" — not 4040010008
# "Phous Maziwa", which is a different item; and "Rapeseed/Canola" is one plant
# and one item here.
ITEM = {
	"limestone": "4040010029",
	"maziwa": "4040010052",
	"wheat_bran": "4040010020",
	"maize_germ": "4040020044",
	"canola": "4040010026",
}

# Westwood Dairy Meal - New formulation. Quantities are the sheet's own kg per
# 1000 kg batch, rounded to a tenth so they sum to exactly 1000.
NEW_CONCENTRATE = "4040010086"
FORMULA = [
	("limestone", 10.0),
	("maziwa", 15.0),
	("wheat_bran", 307.7),
	("maize_germ", 307.7),
	("canola", 359.6),
]

# The four that already have a recipe. Reported against the sheet rather than
# rewritten: they carry stock history, and a BOM that has produced stock is not
# something a formulation script should quietly replace.
EXISTING = {
	"Weaner Meal": "weaner/yearling meal",
	"Weaners/Yearlings": "yearling meal (bullying heifers)",
	"Dry Cows  Meal": "dry meal",
	"Calves Meal": "calf meal",
}


def _resolve():
	rows, missing = [], []
	for key, qty in FORMULA:
		code = ITEM[key]
		if not frappe.db.exists("Item", code):
			missing.append(f"{key} ({code})")
			continue
		rows.append((code, flt(qty)))
	return rows, missing


def _company():
	"""The company the livestock module books against."""
	return (
		frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		or frappe.db.get_value(
			"BOM", {"item": "Weaner Meal", "docstatus": 1}, "company", order_by="modified desc"
		)
	)


def _mixing_farm():
	"""The farm whose store mixes the feed, for BOM.custom_farm."""
	wh = frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse")
	if wh:
		farm = frappe.db.get_value("Warehouse", wh, "custom_farm")
		if farm:
			return farm
	# Fall back to whatever the existing feed BOMs use, so a site that has not
	# set the WIP warehouse still lands somewhere a person chose.
	return frappe.db.get_value(
		"BOM", {"custom_farm": ["is", "set"]}, "custom_farm", order_by="modified desc"
	)


def _existing_bom():
	return frappe.db.get_value(
		"BOM", {"item": NEW_CONCENTRATE, "docstatus": 1, "is_active": 1}, "name"
	)


def build_bom(apply_=False):
	rows, missing = _resolve()
	if missing:
		print("  ! not built — these are not on this site: {}".format(", ".join(missing)))
		return None
	total = sum(q for _, q in rows)
	if abs(total - BATCH_KG) > 0.05:
		print(f"  ! not built — the formula sums to {total:.2f} kg, not {BATCH_KG:.0f}")
		return None

	existing = _existing_bom()
	if existing:
		print(f"  · {NEW_CONCENTRATE} already has an active BOM: {existing}")
		return existing

	name = frappe.db.get_value("Item", NEW_CONCENTRATE, "item_name")
	print("  {} {} — one batch of {:.0f} kg".format("+" if apply_ else "~", name, BATCH_KG))
	for code, qty in rows:
		label = frappe.db.get_value("Item", code, "item_name") or code
		print(f"       {label[:38]:<38} {qty:>8.1f} kg   ({qty / BATCH_KG * 100:.1f}%)")
	if not apply_:
		return None

	doc = frappe.new_doc("BOM")
	doc.item = NEW_CONCENTRATE
	doc.quantity = BATCH_KG
	doc.uom = RECIPE_UOM
	doc.is_active = 1
	doc.is_default = 1
	# The app's own default, not whatever Company happens to sort first. Picking
	# arbitrarily landed this BOM on "Test PCV Company", whose currency is not
	# KES — so a 0.00774 conversion multiplied every ingredient rate by ~129 and
	# costed the batch at 2,473/kg against the sheet's 40.21.
	doc.company = _company()
	farm = _mixing_farm()
	if farm:
		# `custom_farm` is a mandatory Link on BOM here. Derived from the store
		# that does the mixing rather than hardcoded: Livestock Settings names
		# the feed WIP warehouse, and that warehouse names its farm. Every feed
		# store on this site sits on Kapkolia, which is where the mixer is —
		# "Westwood" is the dairy's brand, not the site of the feed operation.
		doc.custom_farm = farm
	# The concentrate is consumed as stock by the TMR Work Orders, which run
	# with use_multi_level_bom = 0 — so this one has to have been mixed first.
	doc.with_operations = 0
	for code, qty in rows:
		doc.append("items", {"item_code": code, "qty": qty, "uom": RECIPE_UOM})
	doc.insert(ignore_permissions=True)
	doc.submit()
	frappe.db.set_value("Item", NEW_CONCENTRATE, "default_bom", doc.name)
	frappe.db.commit()
	print(f"  + built {doc.name}")
	return doc.name


def unlist_as_bought_in(apply_=False):
	"""It is mixed here, so it does not belong on the bought-in list.

	`feeding._engine` answers a shortage of a bought-in concentrate with "buy
	more" and of a mixed one with a Work Order. Leaving it listed would keep the
	new BOM unreachable from the feed screen.
	"""
	settings = frappe.get_single("Livestock Settings")
	rows = [r for r in (settings.bought_in_concentrates or []) if r.item == NEW_CONCENTRATE]
	if not rows:
		print("  · already not listed as bought in")
		return
	if not apply_:
		print(f"  ~ would remove {NEW_CONCENTRATE} from bought_in_concentrates")
		return
	settings.bought_in_concentrates = [
		r for r in settings.bought_in_concentrates if r.item != NEW_CONCENTRATE
	]
	settings.flags.ignore_links = True
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	print(f"  - removed {NEW_CONCENTRATE} from bought_in_concentrates")


def report_existing():
	print("\n[the four that already have a recipe — reported, not rewritten]")
	for item, what in EXISTING.items():
		bom = frappe.db.get_value(
			"BOM", {"item": item, "docstatus": 1, "is_active": 1, "is_default": 1}, "name")
		if not bom:
			print(f"   ! {item[:22]:<22} {what:<34} no default BOM")
			continue
		qty = flt(frappe.db.get_value("BOM", bom, "quantity"))
		lines = frappe.get_all("BOM Item", filters={"parent": bom},
		                       fields=["item_code", "qty"], order_by="idx")
		print(f"   · {item[:22]:<22} {what:<34} {bom} ({qty:.0f} kg batch, {len(lines)} lines)")


def run(apply=False):
	apply_ = bool(apply)
	print("MODE:", "APPLY" if apply_ else "dry run")
	print("\n[lactating concentrate]")
	build_bom(apply_)
	print("\n[bought-in list]")
	unlist_as_bought_in(apply_)
	report_existing()
	print("\nnote: a week's mix is a Work Order for as many 1000 kg batches as the")
	print("      herds require; manufacture_concentrate scales a partial batch.")


def apply_now():
	"""Zero-argument entry point — see the note at the top about bench execute."""
	return run(apply=True)
