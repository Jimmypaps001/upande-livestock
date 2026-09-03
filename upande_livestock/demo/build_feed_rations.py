# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Build the six herd rations from the August 2026 formulations.

ONE UNIT PER HEAD. The BOM produces exactly 1 `Livestock Meal` of a herd's
ration, and its ingredient quantities are the per-head amounts. Manufacturing
for fifty cows is then a Work Order for 50 units, and every raw material scales
by fifty on its own. The old shape put the per-head kilograms in BOM.quantity,
which read as "this recipe makes 14.85 kg" when it meant "this is one cow's
day" — true but confusing, and it made the finished TMR look like bulk stock
rather than a count of meals.

The ration items already hold stock — 64 tonnes of Lactating Group 1 alone — so
their stock UOM cannot be changed to Livestock Meal without writing that off.
Instead each gets a UOM conversion: one meal weighs what one animal's ration
weighs. The Work Order is then counted in meals and the ledger still moves in
kilograms, which is what the store actually holds.

NOTHING IS CREATED FROM THE SPREADSHEET. Every ingredient resolves to an item
that already exists on the site, by explicit code. A name that does not resolve
is reported and its ration is skipped — inventing an item from a formulation
sheet is how a phantom product ends up in a stock ledger.

    bench --site <site> execute upande_livestock.demo.build_feed_rations.run
    bench --site <site> execute upande_livestock.demo.build_feed_rations.apply_now

The --kwargs form does not work: `bench execute` only imports the module on the
no-argument path, so passing arguments makes it eval a dotted name it never
imported and the call dies with a bare NameError naming the app.
"""

import frappe
from frappe.utils import flt

MEAL_UOM = "Livestock Meal"

# Every quantity in the formulation sheet is stated in kilograms, including hay,
# which this site stocks in bales. Saying so explicitly on each BOM line lets
# ERPNext convert; leaving it to default silently reads the number as bales.
RECIPE_UOM = "Kilogram"

# Resolved against kaitet's item master by fuzzy name and then pinned here, so
# the mapping is reviewable rather than recomputed differently on each run.
ITEM = {
	"limestone": "4040010029",
	"maziwa": "4040010052",
	"wheat_bran": "4040010020",
	"maize_germ": "4040020044",
	"canola": "4040010026",          # "Rapeseed/Canola" — the same plant
	"maclick_plus": "4040010002",
	"maclick_dry": "4040010078",
	"ckl_extra_legend": "4040010088",
	"soya": "4040010037",
	"milk_replacer": "4040010095",
	"hay": "4040010034",
	"silage": "4040010082",          # see SILAGE below
}

# The sheet prices sorghum and maize silage separately (7.20 and 10.00), but the
# site carries one farm-produced silage item. Both lines therefore resolve to it
# and are summed. Splitting them needs two items and two stock streams, which is
# a decision about how the pits are managed, not something to infer here.
SILAGE_NOTE = "sorghum and maize silage are one item on this site and are summed"

# The concentrates. Four already exist with their own BOMs; the lactating one
# does not — see UNRESOLVED at the end of run().
CONCENTRATE = {
	"weaner_meal": "Weaner Meal",
	# The sheet's YEARLING MEAL. This used to point at "Weaners/Yearlings",
	# which is not a concentrate at all — it is the weaner herd's TMR, so the
	# bullying-heifer ration was nesting one TMR inside another. The naming on
	# this site is consistent once you see it: "<herd name>" is a TMR and
	# "<x> Meal" is the concentrate that goes into it.
	"yearling_meal": "Bullying Heifer Meal",
	"dry_meal": "Dry Cows  Meal",
	"calf_meal": "Calves Meal",
	"new_concentrate": "4040010086",   # Westwood Dairy Meal - New formulation
}

# (ration item, herd it feeds, [(item key, per-head qty)])
RATIONS = [
	("Lactating Group 1", "Lactating group 1", [
		("silage", 10.0), ("silage", 25.0), ("hay", 2.0), ("new_concentrate", 9.0)]),
	("Lactating Group 2", "LACTATION GROUP 2", [
		("silage", 10.0), ("silage", 25.0), ("hay", 2.0), ("new_concentrate", 6.0)]),
	# "Weaners/Yearlings" is this herd's TMR — the earlier note that no ration
	# item existed was wrong, and followed from the same confusion that had it
	# serving as the bullying heifers' concentrate.
	("Weaners/Yearlings", "4-12 MONTHS (WEANERS)", [
		("silage", 7.0), ("hay", 2.0), ("weaner_meal", 3.0)]),
	("Bullying Heifers", "12 MONTHS-SERVICE (BULLYING HEIFERS)", [
		("silage", 10.0), ("hay", 4.0), ("yearling_meal", 4.0)]),
	("Dry/Steamers/Incalf Heifers", "INCALF HEIFERS", [
		("silage", 8.0), ("silage", 5.0), ("hay", 5.0), ("dry_meal", 2.0)]),
	("TMR Calves Meal", "0-2", [
		("hay", 2.0), ("calf_meal", 2.0), ("milk_replacer", 0.75)]),
]
# Steamers shares the dry ration; mapped after the loop.
ALSO_FEEDS = {
	"Dry/Steamers/Incalf Heifers": ["STEAMERS"],
	"TMR Calves Meal": ["2-4"],
}

# Herds the sheet feeds but the site has no ration item for. Reported, never
# invented — naming a product is the farm's call, not a script's.
NO_RATION_ITEM = {
	"BULLS": (
		"the sheet groups bulls with calves 0-3, but that line carries 0.75 kg of milk "
		"replacer per head, which is a calf's ration and not a bull's. Left without a "
		"ration deliberately, for the farm to say what a bull is fed"
	),
}


def ensure_recipe_conversions(apply_=False):
	"""Make sure every ingredient can be stated in the recipe's units.

	Hay is stocked in bales and written in kilograms on every formulation, and
	the Item carried no Kilogram row at all — so a "2 kg" line silently became
	"2 bales", fourteen times the feed. ERPNext needs the conversion on the item
	before a BOM line can use it.
	"""
	NEEDED = {"4040010034": ("Kilogram", 0.07)}   # a bale is ~14.3 kg
	for code, (uom, factor) in NEEDED.items():
		if not frappe.db.exists("Item", code):
			continue
		doc = frappe.get_doc("Item", code)
		if doc.stock_uom == uom or any(u.uom == uom for u in doc.uoms or []):
			print("  · {} already states {}".format(code, uom))
			continue
		if not apply_:
			print("  ~ would add {} @ {} to {}".format(uom, factor, code))
			continue
		doc.append("uoms", {"uom": uom, "conversion_factor": factor})
		doc.flags.ignore_links = True
		doc.save(ignore_permissions=True)
		print("  + {} @ {} on {}".format(uom, factor, code))


def ensure_uom(apply_=False):
	"""A meal is a count, not a mass. One unit is one animal's ration for a day."""
	if frappe.db.exists("UOM", MEAL_UOM):
		print("  · UOM {} already exists".format(MEAL_UOM))
		return True
	if not apply_:
		print("  ~ would create UOM {}".format(MEAL_UOM))
		return True
	doc = frappe.new_doc("UOM")
	doc.uom_name = MEAL_UOM
	doc.must_be_whole_number = 0   # a part-batch is legitimate
	doc.insert(ignore_permissions=True)
	print("  + UOM {}".format(MEAL_UOM))
	return True


def _resolve(key):
	code = ITEM.get(key) or CONCENTRATE.get(key)
	if not code:
		return None, "no mapping for {!r}".format(key)
	if not frappe.db.exists("Item", code):
		return None, "{} ({}) is not on this site".format(key, code)
	return code, None


def run(apply=False):
	apply_ = bool(apply)
	print("MODE:", "APPLY" if apply_ else "dry run")
	print("\n[uom]")
	ensure_uom(apply_)
	ensure_recipe_conversions(apply_)

	unresolved, built, skipped = [], [], []
	print("\n[rations]  one BOM unit = one animal's ration for one day")
	for ration_item, herd, lines in RATIONS:
		merged = {}
		problem = None
		for key, qty in lines:
			code, err = _resolve(key)
			if err:
				problem = err
				break
			merged[code] = merged.get(code, 0.0) + flt(qty)
		if problem:
			unresolved.append((ration_item, problem))
			print("  ! {:<30} {}".format(ration_item[:30], problem))
			continue
		if not frappe.db.exists("Item", ration_item):
			unresolved.append((ration_item, "the ration item itself does not exist"))
			print("  ! {:<30} ration item missing".format(ration_item[:30]))
			continue
		if not frappe.db.exists("Herds", herd):
			skipped.append((ration_item, "herd {!r} not on this site".format(herd)))
			print("  · {:<30} herd {!r} absent".format(ration_item[:30], herd))
			continue

		print("  {} {:<30} -> {}".format("+" if apply_ else "~", ration_item[:30], herd))
		for code, qty in merged.items():
			nm = frappe.db.get_value("Item", code, "item_name") or code
			print("       {:<34} {:>8.2f} per head".format(nm[:34], qty))
		if apply_:
			built.append(_build_bom(ration_item, herd, merged))

	# Some rations feed more than one herd.
	for ration_item, herds in ALSO_FEEDS.items():
		for h in herds:
			if not frappe.db.exists("Herds", h):
				continue
			print("  · {:<30} also feeds {}".format(ration_item[:30], h))
			if apply_:
				# Find the BOM that was just built, by being the item's default —
				# not by uom. This filtered on MEAL_UOM while _build_bom writes
				# Kilogram, so it silently matched nothing and the sharing herds
				# were left on whatever they had: STEAMERS on a 12.3 kg ration
				# against the sheet's 20, and 2-4 on a 1000 kg concentrate recipe.
				bom = frappe.db.get_value(
					"BOM",
					{"item": ration_item, "docstatus": 1, "is_default": 1, "is_active": 1},
					"name",
				)
				if bom:
					frappe.db.set_value("Herds", h, "bom", bom)
					frappe.db.commit()

	print("\n" + "=" * 66)
	if unresolved:
		print("UNRESOLVED — nothing was invented for these:")
		for name, why in unresolved:
			print("   {:<32} {}".format(name[:32], why))
	print("note: {}".format(SILAGE_NOTE))
	print("\nHERDS WITH NO RATION — a person has to name the product:")
	for herd, why in NO_RATION_ITEM.items():
		if frappe.db.exists("Herds", herd):
			print("   {:<26} {}".format(herd[:26], why))
	if apply_:
		print("built {} BOM(s): {}".format(len(built), ", ".join(b for b in built if b)))
	return {"built": built, "unresolved": unresolved, "skipped": skipped}


def _meal_weight(merged):
	"""What one animal's ration weighs, for the UOM conversion.

	Summed in the recipe's own units — the sheet states every line in kilograms
	even where the item is stocked in bales, and it is the recipe the mixer works
	to.
	"""
	return sum(flt(q) for q in merged.values())


def _ensure_meal_conversion(item_code, weight):
	"""One Livestock Meal of this ration weighs `weight`.

	Without it a Work Order for 50 meals would post 50 kg rather than 50 rations.
	"""
	doc = frappe.get_doc("Item", item_code)
	for row in doc.uoms or []:
		if row.uom == MEAL_UOM:
			if flt(row.conversion_factor) != flt(weight):
				row.conversion_factor = weight
				doc.flags.ignore_links = True
				doc.save(ignore_permissions=True)
			return
	doc.append("uoms", {"uom": MEAL_UOM, "conversion_factor": weight})
	# These item records carry links to masters that no longer exist. Adding a
	# UOM row should not be where that gets discovered.
	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True)


def _bom_farm():
	"""custom_farm is mandatory on BOM here. Taken from the store the feed comes
	out of rather than hardcoded, so it follows the site rather than this file."""
	store = frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse")
	return frappe.db.get_value("Warehouse", store, "custom_farm") if store else None


def _build_bom(ration_item, herd, merged):
	"""One BOM, one unit, per-head quantities."""
	existing = frappe.db.get_value(
		"BOM", {"item": ration_item, "docstatus": 1, "uom": MEAL_UOM}, "name"
	)
	if existing:
		print("       (already built as {})".format(existing))
		frappe.db.set_value("Herds", herd, "bom", existing)
		return existing

	weight = _meal_weight(merged)
	_ensure_meal_conversion(ration_item, weight)
	print("       1 {} = {:g} (the ration's own weight)".format(MEAL_UOM, weight))

	farm = _bom_farm()
	if not farm:
		print("       ! no farm resolved for the BOM — skipped")
		return None

	bom = frappe.new_doc("BOM")
	bom.item = ration_item
	bom.quantity = 1                     # one meal
	bom.uom = MEAL_UOM
	bom.custom_farm = farm
	bom.company = frappe.db.get_single_value("Livestock Settings", "custom_default_company")
	bom.is_active = 1
	bom.is_default = 1
	bom.with_operations = 0
	for code, qty in merged.items():
		row = bom.append("items", {})
		row.item_code = code
		row.qty = qty
		# The sheet states every line in kilograms, including hay, which is
		# STOCKED in bales. Leaving the UOM to default gives "2 BALE" where the
		# recipe means 2 kg — a fourteen-fold error that reads as plausible.
		row.uom = RECIPE_UOM
	bom.insert(ignore_permissions=True)
	bom.submit()
	frappe.db.set_value("Herds", herd, "bom", bom.name)
	frappe.db.commit()
	return bom.name


def apply_now():
	"""Zero-argument entry point — see the note at the top about bench execute."""
	return run(apply=True)
