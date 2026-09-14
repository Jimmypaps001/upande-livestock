# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Build the herd rations from the September 2026 formulations.

THE BOM PRODUCES ONE ANIMAL'S RATION, STATED IN KILOGRAMS. `BOM.quantity` is
what one head eats in a day and the ingredient lines are the per-head amounts,
so the two sum to the same number. Manufacturing for fifty cows is a Work Order
for fifty times that, and every raw material scales with it.

An earlier build tried to count the output in `Livestock Meal` — quantity 1,
one unit per head, with a UOM conversion carrying the weight — because "makes
14.85 kg" reads oddly for what is one cow's day. IT CANNOT WORK, and it failed
silently. ERPNext's `BOM.validate_main_item` assigns

    self.uom = frappe.db.get_value("Item", self.item, "stock_uom")

unconditionally, on every save. The `Livestock Meal` written here was discarded
every time and the BOM came back in Kilogram — so `quantity = 1` stopped
meaning "one ration" and started meaning "one kilogram". Every herd BOM on this
site said it produced 1 kg of TMR while consuming eighteen to forty kilograms
of feed per head. The ration items hold stock (64 tonnes of Lactating Group 1
alone), so changing their stock UOM instead is not open either.

The lesson is in the shape of the fix: a BOM's unit is the item's unit, and the
only number the BOM controls is how much of it one run makes.

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
	"sorghum": "4040010091",         # Sorghum Silage (Bargrazer) - farm produced
}

# THE PITS ARE NOW MANAGED SEPARATELY. The August build merged sorghum and maize
# silage onto one farm-produced item and noted that splitting them "needs two
# items and two stock streams, which is a decision about how the pits are
# managed, not something to infer here". The farm has since made that decision:
# the September formulations carry Sorghum Silage (Bargrazer) as its own line
# against its own item, in five of the seven rations. So they are no longer
# summed, and a ration that draws on both draws on both stocks.
SILAGE_NOTE = "sorghum silage is its own item and its own stock stream since September"

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
#
# The September 2026 revision, read off the farm's live BOMs rather than retyped
# from the sheet. Two things changed against August: sorghum silage joins five
# of the rations as its own line, and the mineral (High Phosphorous "Maziwa")
# appears on the lactating rations, which it did not before.
#
# NOTE FOR THE FARM — the 0-2 ration lost its milk replacer in this revision.
# August carried 0.75 kg per head; September is hay and calves meal only. That
# is either a change in how the youngest calves are fed or a line dropped by
# accident when the recipe was edited, and it is not a script's place to put it
# back. Flagged in the run output every time.
RATIONS = [
	("Lactating Group 1", "Lactating group 1", [
		("new_concentrate", 11.0), ("silage", 23.0), ("maziwa", 0.15),
		("hay", 1.5), ("sorghum", 5.0)]),
	("Lactating Group 2", "LACTATION GROUP 2", [
		("new_concentrate", 9.0), ("silage", 20.0), ("maziwa", 0.15),
		("hay", 2.0), ("sorghum", 5.0)]),
	# The third lactating group had no ration on this site at all, which is why
	# its herd sat with an empty BOM while the other two were fed.
	("Lactating Group 3", "Lactation Group 3 TEST HERD", [
		("new_concentrate", 8.0), ("silage", 20.0), ("maziwa", 0.13), ("hay", 1.5)]),
	# "Weaners/Yearlings" is this herd's TMR — the earlier note that no ration
	# item existed was wrong, and followed from the same confusion that had it
	# serving as the bullying heifers' concentrate.
	("Weaners/Yearlings", "4-12 MONTHS (WEANERS)", [
		("weaner_meal", 3.0), ("hay", 2.0), ("silage", 7.0), ("sorghum", 1.0)]),
	("Bullying Heifers", "12 MONTHS-SERVICE (BULLYING HEIFERS)", [
		("silage", 10.0), ("yearling_meal", 4.0), ("hay", 4.0), ("sorghum", 1.0)]),
	("Dry/Steamers/Incalf Heifers", "INCALF HEIFERS", [
		("dry_meal", 2.0), ("silage", 13.0), ("hay", 2.0), ("sorghum", 1.0)]),
	("TMR Calves Meal", "0-2", [
		("calf_meal", 2.0), ("hay", 1.0)]),
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
				# not by uom. This once filtered on a UOM the BOM never kept, so
				# it silently matched nothing and the sharing herds were left on
				# whatever they had: STEAMERS on a 12.3 kg ration against the
				# sheet's 20, and 2-4 on a 1000 kg concentrate recipe.
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
	print("note: the 0-2 ration no longer carries milk replacer — August had "
	      "0.75 kg per head. Worth a word with the farm before this is trusted.")
	print("\nHERDS WITH NO RATION — a person has to name the product:")
	for herd, why in NO_RATION_ITEM.items():
		if frappe.db.exists("Herds", herd):
			print("   {:<26} {}".format(herd[:26], why))
	if apply_:
		print("built {} BOM(s): {}".format(len(built), ", ".join(b for b in built if b)))
	return {"built": built, "unresolved": unresolved, "skipped": skipped}


def _ration_weight(merged):
	"""What one animal's ration weighs — the BOM's output quantity.

	Summed in the recipe's own units: the formulation states every line in
	kilograms even where the item is stocked in bales, and it is the recipe the
	mixer works to. Output and lines therefore agree by construction, which is
	the invariant the live site's own BOMs break — six of its seven rations
	carry a quantity left over from before their lines were last edited, so
	they issue less TMR than they consume feed.
	"""
	return sum(flt(q) for q in merged.values())


def _stamp_standing(bom_name, herd):
	"""Mark a BOM as this herd's standing ration.

	The same three fields `patches/backfill_standing_ration_boms.py` writes, set
	here at the moment the ration is built rather than waiting for a patch that
	has already run once and will not run again. Without them a new ration is
	invisible to `ration_history` and to every screen that asks a BOM which herd
	it belongs to.

	`custom_farm` is mended on the way past. It is mandatory on BOM now but was
	not always, so a ration carried over from an earlier build has none — and a
	tuned copy of it cannot save, which is how a missing value on a record
	nobody edits surfaces as a failure somewhere else entirely.
	"""
	# A price list that is not on the site. Legacy rations carry
	# `buying_price_list = "Standard Buying"` from a template; this site has no
	# Price List records at all and costs raw materials by Valuation Rate, so
	# the field is dead weight — until something copies the BOM, at which point
	# the copy will not save and the failure names the price list rather than
	# the ration. Cleared, not repointed: there is nothing to point it at.
	price_list = frappe.db.get_value("BOM", bom_name, "buying_price_list")
	if price_list and not frappe.db.exists("Price List", price_list):
		frappe.db.set_value("BOM", bom_name, "buying_price_list", None, update_modified=False)

	# `BOM.is_default` and `Item.default_bom` are two halves of one fact, kept in
	# step by ERPNext's own `manage_default_bom` — which a `db.set_value` walks
	# straight past. A ration carried over from an earlier build can therefore be
	# the default and have the item pointing at nothing, which reads as "this
	# herd has no recipe" everywhere except the BOM itself. Mended here.
	if frappe.db.get_value("BOM", bom_name, "is_default"):
		item = frappe.db.get_value("BOM", bom_name, "item")
		if frappe.db.get_value("Item", item, "default_bom") != bom_name:
			frappe.db.set_value("Item", item, "default_bom", bom_name, update_modified=False)

	values = {
		"custom_herd": herd,
		"custom_is_livestock_feed": 1,
		"custom_ration_kind": "Standing",
	}
	if not frappe.db.get_value("BOM", bom_name, "custom_farm"):
		farm = _bom_farm()
		if farm:
			values["custom_farm"] = farm
	for field, value in values.items():
		if frappe.db.has_column("BOM", field):
			frappe.db.set_value("BOM", bom_name, field, value, update_modified=False)


def _bom_farm():
	"""custom_farm is mandatory on BOM here. Taken from the store the feed comes
	out of rather than hardcoded, so it follows the site rather than this file."""
	store = frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse")
	return frappe.db.get_value("Warehouse", store, "custom_farm") if store else None


def _same_recipe(bom_name, merged):
	"""Does this BOM already say exactly what the formulation says?

	Compared line by line AND against the output, not by name or by date. A
	recipe is its quantities.

	The output is part of the comparison because this site is full of rations
	whose lines are right and whose quantity says 1 — the wreckage of the
	`Livestock Meal` attempt described at the top of this file. Matching on
	lines alone would adopt one of those as "unchanged" and quietly keep the
	bug alive.
	"""
	if abs(flt(frappe.db.get_value("BOM", bom_name, "quantity"))
	       - flt(sum(merged.values()))) > 0.0005:
		return False
	rows = frappe.get_all("BOM Item", filters={"parent": bom_name},
	                      fields=["item_code", "qty"])
	if len(rows) != len(merged):
		return False
	for r in rows:
		want = merged.get(r.item_code)
		if want is None or abs(flt(r.qty) - flt(want)) > 0.0005:
			return False
	return True


def _build_bom(ration_item, herd, merged):
	"""One BOM, one unit, per-head quantities.

	A CHANGED FORMULATION MAKES A NEW BOM, not an edit. A submitted BOM seals:
	ERPNext refuses "Not allowed to change Qty after submission", and there is
	nowhere to put the new numbers. So the recipe that matches is reused and a
	recipe that does not is superseded — the old revision stays submitted and
	readable, which is what every feed run already posted against it needs.
	"""
	# Matched on the recipe, never on the UOM: ERPNext overwrites BOM.uom with
	# the item's stock UOM on every save, so it distinguishes nothing here.
	for candidate in frappe.get_all(
		"BOM", filters={"item": ration_item, "docstatus": 1},
		pluck="name", order_by="creation desc",
	):
		if _same_recipe(candidate, merged):
			print("       (unchanged — already built as {})".format(candidate))
			frappe.db.set_value("Herds", herd, "bom", candidate)
			if not frappe.db.get_value("BOM", candidate, "is_default"):
				frappe.db.set_value("BOM", candidate, {"is_default": 1, "is_active": 1})
			_stamp_standing(candidate, herd)
			frappe.db.commit()
			return candidate
	superseded = frappe.db.get_value(
		"BOM", {"item": ration_item, "docstatus": 1, "is_default": 1}, "name")
	if superseded:
		print("       (supersedes {})".format(superseded))

	weight = _ration_weight(merged)
	print("       one head's day = {:g} kg".format(weight))

	farm = _bom_farm()
	if not farm:
		print("       ! no farm resolved for the BOM — skipped")
		return None

	bom = frappe.new_doc("BOM")
	bom.item = ration_item
	# One run of this BOM makes one animal's ration. The lines sum to the same
	# number, so a Work Order for the herd scales both sides together.
	bom.quantity = weight
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
	_stamp_standing(bom.name, herd)
	frappe.db.set_value("Herds", herd, "bom", bom.name)
	frappe.db.commit()
	return bom.name


def apply_now():
	"""Zero-argument entry point — see the note at the top about bench execute."""
	return run(apply=True)
