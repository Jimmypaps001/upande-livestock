# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Mutara's real data: its feeds, herds, rations, tagged animals and labour, from its own tracker.

    bench --site mutara.local execute upande_livestock.demo.seed_mutara_tracker.execute

Run by hand on mutara.local only (refuses any site that is not `.local` unless force=True). Reads
demo/data/mutara_tracker.json, which scripts/extract_mutara_tracker.py extracts from the farm's
spreadsheet; the JSON's `notes` list every judgement made on the sheet's data.

Idempotent: everything is looked up before it is written, so a second run changes nothing.

What it does
------------
* Feed Items for the 23 feeds on "Feed Rates" (and the two the shoat batch adds), in the feed item
  group, stocked in kilograms; additives dosed per head carry a Gram / Millilitre conversion. A Diesel
  item. All received into stock ONCE at the sheet's prices, so the stock ledger has a valuation.
* A Livestock Feed record per bought feed with book DM / CP / ME / NDF (nutrient_source Book value)
  and, where the field exists, its substitute group.
* Herds as the farm names them, with the ration sheet's standing rations and the Shoat Concentrate
  (the 1000 kg batch) as a made concentrate. Cattle mix from raw, shoats use the made batch, where
  `concentrate_mode` exists.
* Tagged animals from the RFID tabs with their weighings.
* Livestock Daily Labour history, when that doctype exists; the Mixer Wagon's diesel as issues from
  the Fuel Store against the feedlot cost centre.
* The old demo herds, flocks, feeds and animals are retired: disabled, never deleted.

Fields other builds add (Livestock Feed.substitute_group, Herds.concentrate_mode, Livestock Settings
feed_by_head_count, the Livestock Daily Labour doctype) are written only when they exist, so this runs
before and after those land.
"""

import re
from datetime import date

import frappe
from frappe.utils import flt, getdate

from upande_livestock.demo import mutara_tracker_data as data_mod

COMPANY = "Mutara"
FARM = "Mutara"
OPENING_DATE = date(2026, 1, 2)          # before the first fuel issue (4 Jan 2026), inside fiscal year 2026
OPENING_REMARK = "Mutara tracker: opening stock at Feed Rates prices"
FUEL_REMARK = "Mutara tracker: {machine} diesel {date}"
SEED_TAG = "seed:mutara-tracker"

FEEDLOT_COST_CENTER = "Feedlot"
FUEL_STORE = "Fuel Store"
FUEL_GROUP = "Fuel"
DIESEL = "Diesel"

# Where each feed is kept (stores made by demo/seed_mutara_stores).
STORE = {
	"Maize Silage": "Silo", "Sorghum Silage": "Silo", "Chopped Maize": "Silo",
	"Hay": "Hay Store", "Lucerne": "Hay Store",
	"Napier": "Feed Store", "Vines": "Feed Store", "Feed Potatoes": "Feed Store",
}
DEFAULT_STORE = "Concentrate Store"

# Book values, rounded, for these feeds as fed in East Africa (Feedipedia / NRC ranges, Kenyan feed
# tables). DM is % as fed; CP, NDF, fat, Ca, P are % of DM; ME is MJ per kg DM. Branded premixes and
# additives get dry matter only: their label is the source, and a guessed analysis would be worse than
# none. Replace any of these with a lab analysis or the supplier's label.
BOOK = {
	"Lucerne": ("Forage", dict(dry_matter_pct=22, crude_protein_pct=19, energy_me_mj_per_kg=9.5, fibre_ndf_pct=42,
	                            fat_pct=2.5, calcium_pct=1.5, phosphorus_pct=0.28)),
	"Vines": ("Forage", dict(dry_matter_pct=13, crude_protein_pct=16, energy_me_mj_per_kg=9.5, fibre_ndf_pct=38,
	                          fat_pct=3, calcium_pct=1.2, phosphorus_pct=0.3)),
	"Napier": ("Forage", dict(dry_matter_pct=18, crude_protein_pct=9, energy_me_mj_per_kg=8.5, fibre_ndf_pct=65,
	                           fat_pct=2, calcium_pct=0.4, phosphorus_pct=0.25)),
	"Maize Silage": ("Forage", dict(dry_matter_pct=30, crude_protein_pct=8, energy_me_mj_per_kg=10.5,
	                                 fibre_ndf_pct=45, fat_pct=3, calcium_pct=0.25, phosphorus_pct=0.22)),
	"Sorghum Silage": ("Forage", dict(dry_matter_pct=28, crude_protein_pct=7.5, energy_me_mj_per_kg=9.5,
	                                   fibre_ndf_pct=55, fat_pct=2.5, calcium_pct=0.35, phosphorus_pct=0.2)),
	"Chopped Maize": ("Forage", dict(dry_matter_pct=25, crude_protein_pct=8, energy_me_mj_per_kg=10.2,
	                                  fibre_ndf_pct=50, fat_pct=2.5, calcium_pct=0.3, phosphorus_pct=0.22)),
	"Hay": ("Forage", dict(dry_matter_pct=90, crude_protein_pct=7, energy_me_mj_per_kg=8.0, fibre_ndf_pct=72,
	                        fat_pct=2, calcium_pct=0.35, phosphorus_pct=0.2)),
	"Maize Grain": ("Energy (grain / by-product)", dict(dry_matter_pct=88, crude_protein_pct=9.5,
	                                                     energy_me_mj_per_kg=13.5, fibre_ndf_pct=11, fat_pct=4,
	                                                     calcium_pct=0.03, phosphorus_pct=0.3)),
	"Wheat Bran": ("Energy (grain / by-product)", dict(dry_matter_pct=89, crude_protein_pct=16,
	                                                    energy_me_mj_per_kg=11.0, fibre_ndf_pct=45, fat_pct=4,
	                                                    calcium_pct=0.12, phosphorus_pct=1.1)),
	"Wheat Pollard": ("Energy (grain / by-product)", dict(dry_matter_pct=88, crude_protein_pct=16,
	                                                       energy_me_mj_per_kg=12.0, fibre_ndf_pct=35, fat_pct=4,
	                                                       calcium_pct=0.1, phosphorus_pct=0.9)),
	"Feed Potatoes": ("Energy (grain / by-product)", dict(dry_matter_pct=21, crude_protein_pct=10,
	                                                       energy_me_mj_per_kg=13.0, fibre_ndf_pct=8, fat_pct=0.5,
	                                                       calcium_pct=0.05, phosphorus_pct=0.25)),
	"Molasses": ("Energy (grain / by-product)", dict(dry_matter_pct=75, crude_protein_pct=5, energy_me_mj_per_kg=12.0,
	                                                  fibre_ndf_pct=0, fat_pct=0.1, calcium_pct=0.9,
	                                                  phosphorus_pct=0.1)),
	"Sunflower Cake": ("Protein", dict(dry_matter_pct=91, crude_protein_pct=30, energy_me_mj_per_kg=10.0,
	                                    fibre_ndf_pct=40, fat_pct=8, calcium_pct=0.4, phosphorus_pct=1.0)),
	"Canola": ("Protein", dict(dry_matter_pct=89, crude_protein_pct=38, energy_me_mj_per_kg=12.0, fibre_ndf_pct=28,
	                            fat_pct=3.5, calcium_pct=0.7, phosphorus_pct=1.1)),
	"Soyabean Meal": ("Protein", dict(dry_matter_pct=89, crude_protein_pct=48, energy_me_mj_per_kg=13.0,
	                                   fibre_ndf_pct=14, fat_pct=2, calcium_pct=0.35, phosphorus_pct=0.7)),
	"Limestone": ("Mineral & vitamin", dict(dry_matter_pct=99, calcium_pct=36, phosphorus_pct=0)),
	"DCP": ("Mineral & vitamin", dict(dry_matter_pct=97, calcium_pct=22, phosphorus_pct=18)),
	"Mineral Salt": ("Mineral & vitamin", dict(dry_matter_pct=99)),
	"Vital Nyama": ("Mineral & vitamin", dict(dry_matter_pct=98)),
	"Vital Kondoo": ("Mineral & vitamin", dict(dry_matter_pct=98)),
	"Vital Dry": ("Mineral & vitamin", dict(dry_matter_pct=98)),
	"Zincur": ("Additive", dict(dry_matter_pct=98)),
	"Diamond V": ("Additive", dict(dry_matter_pct=92)),
	"Meat Boost": ("Additive", dict(dry_matter_pct=92)),
	# A liquid dosed in ml. Its label gives no dry matter; 70 % is a molasses-carrier liquid supplement's,
	# there only because Livestock Feed requires a dry matter for a raw feed.
	"Meat Grower": ("Additive", dict(dry_matter_pct=70)),
}
BOOK_NOTE = "Typical book value, rounded (Mutara tracker seed). Replace with a lab analysis or the supplier's label."
NUTRIENT_FIELDS = ("dry_matter_pct", "crude_protein_pct", "carbohydrate_pct", "fibre_ndf_pct", "fat_pct",
                   "energy_me_mj_per_kg", "calcium_pct", "phosphorus_pct")

# Wet forages a mixer operator swaps for one another; kilograms adjusted by dry matter (spec Part D.5).
SUBSTITUTE_GROUPS = {
	"Wet forage": ["Maize Silage", "Chopped Maize", "Napier", "Sorghum Silage", "Vines"],
}

# Cattle herds as the farm names them: (class, min kg, max kg).
#
# WEIGHT BANDS. The farm's own sheets disagree. "Feed lot rations 2026" heads its columns
# "FINISHERS (above 280kgs)" and "GROWERS(150-279KGS)"; the RFID tabs are named "280-up Finishers",
# "250-up growers 1" and "250-down growers 2", which reads as a growers band ending at 250. The tabs
# are the farm's working weighing lists, so their names decide: Finishers start at 280 kg (both agree);
# Growers run up to 280, and since no tab names a lower limit the ration sheet's 150 kg is kept. The
# 250 kg split is two weighing lists within Growers, not a herd boundary. Starters/Breeders also holds
# breeders, so it is not a weight band (class Other); the ladder starts at Growers.
CATTLE_HERDS = {
	"Finishers": ("Fattening", 280, 0),
	"Growers": ("Fattening", 150, 280),
	"Starters/Breeders": ("Other", 0, 0),
	"Quarantine": ("Other", 0, 0),
	"In-calf": ("Breeding", 0, 0),
	"Heifers": ("Other", 0, 0),
	"Lactating": ("Breeding", 0, 0),
}
CATTLE_CONCENTRATE_MODE = "Mix from raw"
SHOAT_CONCENTRATE_MODE = "Pre-manufacture"
SHOAT_SPECIES = "Sheep"          # the groups mix sheep and goats; a herd has one species (see the JSON notes)

# The demo placeholders this replaces.
RETIRED_HERDS = ["Lactation Group 1", "Lactation Group 2", "Bulling Heifers", "Weaner Heifers", "Bull Reserve",
                 "Starters"]
RETIRED_FLOCKS = ["Dorper Flock", "Red Maasai Flock", "Galla Goat Herd", "Boer Goat Herd"]
RETIRED_FEEDS = ["Mutara Beef Meal", "Mutara Shoat Pellets", "Mutara Boma Hay", "Mutara Maize Silage",
                 "Mutara Mineral Lick"]
RETIRE_DATE = date(2026, 11, 9)          # the tracker's latest day
DEMO_HERD = "Demo (retired)"
DEMO_TAG = re.compile(r"^[AB]\d{3}/\d{2}$")   # demo/seed_mutara_beef's tags; real tags are RFID numbers


def _log(m):
	print("  " + m)


def _abbr():
	return frappe.db.get_value("Company", COMPANY, "abbr")


def _full(name):
	return "{} - {}".format(name, _abbr())


def _has(doctype, field):
	return frappe.db.exists("DocType", doctype) and frappe.get_meta(doctype).has_field(field)


def _select_ok(doctype, field, value):
	"""Can `value` be written to this field? A Select only takes one of its options."""
	if not _has(doctype, field):
		return False
	df = frappe.get_meta(doctype).get_field(field)
	if df.fieldtype == "Select":
		return value in (df.options or "").split("\n")
	return True


def _set_if_changed(doctype, name, values):
	have = frappe.db.get_value(doctype, name, list(values), as_dict=True) or {}
	changed = {k: v for k, v in values.items() if (have.get(k) or None) != (v or None)
	           and not (isinstance(v, (int, float)) and flt(have.get(k)) == flt(v))}
	if changed:
		frappe.db.set_value(doctype, name, changed)
	return changed


def _ration_item(herd):
	return "Ration - " + herd.replace("/", " and ")


def _operator():
	return frappe.db.get_value("Employee", {"user_id": "saitoti@mutaraorchards.com"}, "name")


# ---------------------------------------------------------------------------
# places, items, stock
# ---------------------------------------------------------------------------


def ensure_cost_center():
	name = _full(FEEDLOT_COST_CENTER)
	if not frappe.db.exists("Cost Center", name):
		frappe.get_doc({"doctype": "Cost Center", "cost_center_name": FEEDLOT_COST_CENTER, "company": COMPANY,
		                "parent_cost_center": _full(COMPANY), "is_group": 0}).insert(ignore_permissions=True)
		_log("cost centre " + name)
	return name


def ensure_fuel_store():
	from upande_livestock.demo.seed_mutara_stores import ensure_warehouse

	store = ensure_warehouse(FUEL_STORE)
	if _has("Production Settings", "fuel_warehouse"):
		if not frappe.db.get_single_value("Production Settings", "fuel_warehouse"):
			frappe.db.set_single_value("Production Settings", "fuel_warehouse", store)
			_log("Production Settings fuel warehouse " + store)
	return store


def _ensure_item(code, group, stock_uom, rate, extra_uoms=()):
	if frappe.db.exists("Item", code):
		doc = frappe.get_doc("Item", code)
		have = {r.uom for r in doc.uoms}
		missing = [(u, f) for u, f in extra_uoms if u not in have]
		if missing:
			for uom, factor in missing:
				doc.append("uoms", {"uom": uom, "conversion_factor": factor})
			doc.save(ignore_permissions=True)
			_log("item {}: dose unit {}".format(code, ", ".join(u for u, _f in missing)))
		return False
	frappe.get_doc({
		"doctype": "Item", "item_code": code, "item_name": code, "item_group": group, "stock_uom": stock_uom,
		"is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0, "include_item_in_manufacturing": 1,
		"valuation_rate": rate,
		"uoms": [{"uom": stock_uom, "conversion_factor": 1}] + [{"uom": u, "conversion_factor": f} for u, f in extra_uoms],
	}).insert(ignore_permissions=True)
	_log("item {} ({}, {} KES)".format(code, stock_uom, rate))
	return True


def ensure_items(data):
	from upande_livestock.serverscripts.feeding.feed_in_store import feed_item_group

	group = feed_item_group()
	doses = data_mod.dose_uoms(data)
	for feed in data["feeds"]:
		stock_uom, dose_uom = doses.get(feed["item"], ("Kilogram", None))
		extra = [(dose_uom, data_mod.DOSE_FACTOR[dose_uom])] if dose_uom else []
		_ensure_item(feed["item"], group, stock_uom, feed["rate"], extra)
	if not frappe.db.exists("Item Group", FUEL_GROUP):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": FUEL_GROUP, "parent_item_group": "All Item Groups",
		                "is_group": 0}).insert(ignore_permissions=True)
	_ensure_item(DIESEL, FUEL_GROUP, "Litre", data["diesel_rate"])
	for item in RETIRED_FEEDS:
		if frappe.db.exists("Item", item) and not frappe.db.get_value("Item", item, "disabled"):
			frappe.db.set_value("Item", item, "disabled", 1)
			_log("retired feed " + item)


def ensure_feed_records(data):
	sub_ok = _has("Livestock Feed", "substitute_group")
	group_of = {item: g for g, items in SUBSTITUTE_GROUPS.items() for item in items}
	if sub_ok:
		_ensure_substitute_groups()
	made = changed = 0
	for feed in data["feeds"]:
		item = feed["item"]
		category, values = BOOK[item]
		if frappe.db.get_value("Livestock Feed", item, "nutrient_source") in ("Lab analysis", "Supplier label"):
			continue          # the farm's own figures win over the book
		want = {"feed_name": item, "category": category, "nutrient_source": "Book value", "notes": BOOK_NOTE,
		        "disabled": 0, **{f: values.get(f, 0) for f in NUTRIENT_FIELDS}}
		if sub_ok and group_of.get(item) and _select_ok("Livestock Feed", "substitute_group", group_of[item]):
			want["substitute_group"] = group_of[item]
		if not frappe.db.exists("Livestock Feed", item):
			frappe.get_doc({"doctype": "Livestock Feed", "item": item, **want}).insert(ignore_permissions=True)
			made += 1
		elif _set_if_changed("Livestock Feed", item, want):
			changed += 1
	for item in RETIRED_FEEDS:
		if frappe.db.exists("Livestock Feed", item):
			_set_if_changed("Livestock Feed", item, {"disabled": 1})
	if made or changed:
		_log("Livestock Feed: {} made, {} updated{}".format(made, changed, "" if sub_ok else
		                                                     " (no substitute_group field yet)"))


def _ensure_substitute_groups():
	"""If substitute_group is a Link, the groups must exist as records of its doctype."""
	df = frappe.get_meta("Livestock Feed").get_field("substitute_group")
	if df.fieldtype != "Link" or not df.options:
		return
	autoname = frappe.get_meta(df.options).autoname or ""
	for group in SUBSTITUTE_GROUPS:
		if frappe.db.exists(df.options, group):
			continue
		doc = frappe.new_doc(df.options)
		if autoname.startswith("field:"):
			doc.set(autoname[len("field:"):], group)
			doc.insert(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True, set_name=group)
		_log("substitute group " + group)


def _has_ledger(item):
	return bool(frappe.db.exists("Stock Ledger Entry", {"item_code": item, "is_cancelled": 0}))


def ensure_opening_stock(data):
	"""One Material Receipt at the Feed Rates prices, of every feed (and the diesel) that has never been in
	stock, so each has a valuation. Thirty days of today's need, rounded; see mutara_tracker_data."""
	qty = data_mod.opening_quantities(data)
	litres = sum(flt(f["litres"]) for f in data["fuel"])
	qty[DIESEL] = int(-(-(litres + 1000) // 100) * 100)        # the sheet's issues and a month in hand
	rate = {f["item"]: flt(f["rate"]) for f in data["feeds"]}
	rate[DIESEL] = flt(data["diesel_rate"])
	rows = [(item, q) for item, q in qty.items() if frappe.db.exists("Item", item) and not _has_ledger(item)]
	if not rows:
		return None
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = se.purpose = "Material Receipt"
	se.company = COMPANY
	se.set_posting_time = 1
	se.posting_date = OPENING_DATE
	se.remarks = OPENING_REMARK
	for item, q in rows:
		store = FUEL_STORE if item == DIESEL else STORE.get(item, DEFAULT_STORE)
		se.append("items", {"item_code": item, "qty": q, "t_warehouse": _full(store), "basic_rate": rate[item],
		                    "allow_zero_valuation_rate": 1 if not rate[item] else 0})
	se.insert(ignore_permissions=True)
	se.submit()
	_log("opening stock {} ({} lines)".format(se.name, len(rows)))
	return se.name


# ---------------------------------------------------------------------------
# retiring the demo
# ---------------------------------------------------------------------------


def _retire_ration(herd):
	bom = frappe.db.get_value("Herds", herd, "bom")
	if not bom:
		return
	frappe.db.set_value("Herds", herd, "bom", None)
	frappe.db.set_value("BOM", bom, {"is_active": 0, "is_default": 0}, update_modified=False)
	item = frappe.db.get_value("BOM", bom, "item")
	if item and item.startswith("Ration - "):
		frappe.db.set_value("Item", item, {"disabled": 1, "default_bom": None})


def retire_demo():
	"""Disable, never delete. A retired herd stops being fed (no ration), leaves the weight ladder and its
	paddock; a flock is counted to nought on the tracker's latest day; a demo animal moves to the
	'Demo (retired)' herd and is disabled. Their history stays readable."""
	from upande_livestock.serverscripts.common import shoats

	disabled_field = _has("Herds", "disabled")
	if not frappe.db.exists("Herds", DEMO_HERD):
		frappe.get_doc({"doctype": "Herds", "herd_name": DEMO_HERD, "herd_class": "Other", "counting": "Individual",
		                "species": "Cattle"}).insert(ignore_permissions=True)
	for herd in RETIRED_HERDS + RETIRED_FLOCKS + [DEMO_HERD]:
		if not frappe.db.exists("Herds", herd):
			continue
		_retire_ration(herd)
		want = {"paddock": None}
		if herd in RETIRED_HERDS + [DEMO_HERD]:
			want.update(herd_class="Other", min_weight_kg=0, max_weight_kg=0)
		if disabled_field:
			want["disabled"] = 1
		if _set_if_changed("Herds", herd, want):
			_log("retired herd " + herd)
	operator = _operator()
	for flock in RETIRED_FLOCKS:
		if not frappe.db.exists("Herds", flock) or frappe.db.get_value("Herds", flock, "counting") != "By number":
			continue
		tag = SEED_TAG + ":retired"
		if frappe.db.exists("Herd Count Event", {"herd": flock, "remarks": tag, "docstatus": 1}):
			continue
		doc = frappe.get_doc({"doctype": "Herd Count Event", "herd": flock, "event_date": str(RETIRE_DATE),
		                      "event_type": "Head Count", "females": 0, "males": 0, "young": 0, "others": 0,
		                      "reason": "Demo flock retired: Mutara's shoats are Shoat Groups 1-7",
		                      "operator": operator, "remarks": tag})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		shoats.rebuild(flock)
		_log("retired flock {} (counted to nought)".format(flock))
	demo = [a.name for a in frappe.get_all("Animal", filters={"disabled": 0}, fields=["name"])
	        if DEMO_TAG.match(a.name)]
	touched = set()
	for name in demo:
		touched.add(frappe.db.get_value("Animal", name, "current_herd"))
		frappe.db.set_value("Animal", name, {"current_herd": DEMO_HERD, "disabled": 1}, update_modified=False)
	if demo:
		from upande_livestock.serverscripts.common.animal import recompute_herd_count

		for herd in touched | {DEMO_HERD}:
			recompute_herd_count(herd)
		_log("{} demo animals moved to {} and disabled".format(len(demo), DEMO_HERD))


# ---------------------------------------------------------------------------
# herds and rations
# ---------------------------------------------------------------------------


def _herd(name, values):
	mode = values.pop("concentrate_mode", None)
	if mode and _select_ok("Herds", "concentrate_mode", mode):
		values["concentrate_mode"] = mode
	if frappe.db.exists("Herds", name):
		if _set_if_changed("Herds", name, values):
			_log("herd {} updated".format(name))
		return
	doc = frappe.get_doc({"doctype": "Herds", "herd_name": name, **values})
	doc.flags.ladder_check_suspended = True        # the whole ladder is judged once, in ensure_herds
	doc.insert(ignore_permissions=True)
	_log("herd " + name)


def ensure_herds(data):
	from upande_livestock.upande_livestock.doctype.herds.herds import _fattening_bands, check_ladder

	cc = _full(FEEDLOT_COST_CENTER)
	for name, (cls, lo, hi) in CATTLE_HERDS.items():
		_herd(name, {"herd_class": cls, "min_weight_kg": lo, "max_weight_kg": hi, "counting": "Individual",
		             "species": "Cattle", "cost_center": cc, "concentrate_mode": CATTLE_CONCENTRATE_MODE})
	for g in data["shoat_groups"]:
		_herd(g["herd"], {"herd_class": "Other", "counting": "By number", "species": SHOAT_SPECIES,
		                  "concentrate_mode": SHOAT_CONCENTRATE_MODE})
	try:
		check_ladder(_fattening_bands())
	except Exception as e:
		print("  WARNING: the weight ladder does not tile: {}".format(e))


def ensure_rations(data):
	from upande_livestock.serverscripts.feeding._concentrate import set_concentrate
	from upande_livestock.serverscripts.feeding._standing_ration import set_standing_ration

	for ration in data["rations"]:
		got = set_standing_ration(ration["herd"], data_mod.ration_lines(ration),
		                          ration_item=_ration_item(ration["herd"]), farm=FARM)
		if got["changed"]:
			_log("ration {}: {} kg a head -> {}".format(ration["herd"], got["per_head_kg"], got["bom"]))
	conc = data["shoat_concentrate"]
	made = set_concentrate(conc["name"], [{"item_code": line["item"], "qty": line["kg"]} for line in conc["lines"]],
	                       farm=FARM)
	if made["changed"]:
		_log("concentrate {}: {} kg batch -> {}".format(conc["name"], made["base_qty"], made["bom"]))
	for g in data["shoat_groups"]:
		got = set_standing_ration(g["herd"], [{"item_code": made["item"], "qty": data_mod.shoat_per_head(g)}],
		                          ration_item=_ration_item(g["herd"]), farm=FARM)
		if got["changed"]:
			_log("ration {}: {} kg a head -> {}".format(g["herd"], got["per_head_kg"], got["bom"]))


# ---------------------------------------------------------------------------
# animals and head counts
# ---------------------------------------------------------------------------


def _burn_name(a):
	return a["old_tag"] or a["tag"].replace(" ", "")[-6:]


def ensure_animals(data):
	made = weighed = 0
	for n, a in enumerate(data["animals"], start=1):
		if not frappe.db.exists("Animal", a["tag"]):
			frappe.get_doc({
				"doctype": "Animal", "tag_number": a["tag"], "burn_name": _burn_name(a), "sex": "Male",
				"species": "Cattle", "origin": "Purchased", "acquisition_date": a.get("acquired"),
				"purchase_value": a.get("cost"), "current_herd": a["herd"], "company": COMPANY, "status": "Active",
				"stream": "Feedlot",
				"remarks": "From the farm's tracker, tab '{}'{}".format(
					a["sheet"], "; bought at {}".format(a["source"]) if a.get("source") else ""),
			}).insert(ignore_permissions=True)
			made += 1
		for w in a["weights"]:
			if frappe.db.exists("Livestock Weight Record", {"animal": a["tag"], "weight_date": w["date"],
			                                                "docstatus": 1}):
				continue
			doc = frappe.get_doc({"doctype": "Livestock Weight Record", "animal": a["tag"], "weight_date": w["date"],
			                      "weight_kg": w["kg"],
			                      "custom_is_backdated": 1 if getdate(w["date"]) < getdate() else 0})
			doc.insert(ignore_permissions=True)
			doc.submit()
			weighed += 1
		if n % 50 == 0:
			frappe.db.commit()
	frappe.db.commit()
	if made or weighed:
		_log("{} animals, {} weighings".format(made, weighed))


def ensure_counts(data):
	"""Herds with tagged animals count them; In-calf, Lactating and Heifers have no tagged animals yet and
	carry the tracker's head; shoat groups open with a head count on the shoat sheet's date."""
	from upande_livestock.serverscripts.common import shoats
	from upande_livestock.serverscripts.common.animal import live_herd_count, recompute_herd_count

	for herd, row in data["herd_counts"].items():
		if row["source"] == "tagged animals" or live_herd_count(herd):
			recompute_herd_count(herd)
		elif int(frappe.db.get_value("Herds", herd, "number_of_animals") or 0) != int(row["count"]):
			frappe.db.set_value("Herds", herd, "number_of_animals", int(row["count"]))
			_log("{}: {} head ({})".format(herd, row["count"], row["source"]))
	on = data["shoat_concentrate"]["date"]
	operator = _operator()
	for g in data["shoat_groups"]:
		tag = SEED_TAG + ":opening"
		if frappe.db.exists("Herd Count Event", {"herd": g["herd"], "remarks": tag, "docstatus": 1}):
			continue
		doc = frappe.get_doc({"doctype": "Herd Count Event", "herd": g["herd"], "event_date": on,
		                      "event_type": "Head Count", "females": 0, "males": 0, "young": 0,
		                      "others": int(g["animals"]), "reason": "Shoats ration 2026: animal count",
		                      "operator": operator, "remarks": tag})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		shoats.rebuild(g["herd"])
		_log("{}: {} head".format(g["herd"], g["animals"]))


# ---------------------------------------------------------------------------
# labour and fuel
# ---------------------------------------------------------------------------


def ensure_labour(data):
	"""Livestock Daily Labour, one per date, if that doctype is installed. Its field names are read off its
	meta (a Date field and a Table of category / workers / day_rate / amount)."""
	dt = "Livestock Daily Labour"
	if not frappe.db.exists("DocType", dt):
		_log("no {} doctype yet: labour history skipped".format(dt))
		return
	meta = frappe.get_meta(dt)
	date_field = next((f.fieldname for f in meta.fields if f.fieldtype == "Date" and f.reqd), None) or \
		next((f.fieldname for f in meta.fields if f.fieldtype == "Date"), None)
	table = next((f for f in meta.fields if f.fieldtype == "Table"), None)
	if not date_field or not table:
		_log("{} has no date or rows field: labour history skipped".format(dt))
		return
	child = frappe.get_meta(table.options)
	made = 0
	for day in data["labour"]:
		if frappe.db.exists(dt, {date_field: day["date"]}):
			continue
		rows = []
		for r in day["rows"]:
			row = {"category": r["category"], "workers": r["workers"], "day_rate": r["day_rate"],
			       "amount": flt(r["workers"]) * flt(r["day_rate"])}
			rows.append({k: v for k, v in row.items() if child.has_field(k)})
		doc = frappe.get_doc({"doctype": dt, date_field: day["date"], table.fieldname: rows})
		doc.flags.ignore_permissions = True
		doc.insert()
		if meta.is_submittable:
			doc.submit()
		made += 1
		if made % 50 == 0:
			frappe.db.commit()
	if made:
		_log("{} days of labour".format(made))


def ensure_fuel(data):
	"""The Mixer Wagon's diesel, issued from the Fuel Store against the feedlot cost centre on the day the
	sheet records it. Only rows with litres; the value is the stock ledger's, not the sheet's."""
	store, cc = _full(FUEL_STORE), _full(FEEDLOT_COST_CENTER)
	made = 0
	for row in data["fuel"]:
		remark = FUEL_REMARK.format(machine=row["machine"], date=row["date"])
		if frappe.db.exists("Stock Entry", {"remarks": remark, "docstatus": 1}):
			continue
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = se.purpose = "Material Issue"
		se.company = COMPANY
		se.set_posting_time = 1
		se.posting_date = row["date"]
		se.remarks = remark
		se.append("items", {"item_code": DIESEL, "qty": row["litres"], "s_warehouse": store, "cost_center": cc})
		se.insert(ignore_permissions=True)
		se.submit()
		made += 1
	if made:
		_log("{} diesel issues".format(made))


def ensure_settings():
	if _has("Livestock Settings", "feed_by_head_count"):
		if not frappe.db.get_single_value("Livestock Settings", "feed_by_head_count"):
			frappe.db.set_single_value("Livestock Settings", "feed_by_head_count", 1)
			_log("Livestock Settings: feed by head count")
	# The heifer herds the beef demo registered are retired; the farm's is Heifers.
	rows = frappe.get_all("Livestock Heifer Herd", filters={"parent": "Livestock Settings"}, fields=["name", "herd"])
	for r in rows:
		if r.herd in RETIRED_HERDS:
			frappe.db.delete("Livestock Heifer Herd", r.name)
			_log("heifer herds: {} removed".format(r.herd))
	if "Heifers" not in {r.herd for r in rows}:
		row = frappe.new_doc("Livestock Heifer Herd")
		row.update({"herd": "Heifers", "parent": "Livestock Settings", "parenttype": "Livestock Settings",
		            "parentfield": "heifer_herds", "idx": len(rows) + 1})
		row.insert(ignore_permissions=True)
		_log("heifer herds: Heifers")
	frappe.clear_document_cache("Livestock Settings", "Livestock Settings")


# ---------------------------------------------------------------------------


def execute(force=False):
	"""Seed Mutara's tracker data. Idempotent; prints what it does. Backdating is opened for the history
	load and put back as it was, even if the run fails."""
	site = frappe.local.site
	if not force and not site.endswith(".local"):
		frappe.throw("{} is not a .local site. Pass force=True only with approval.".format(site))
	was = frappe.db.get_single_value("Livestock Settings", "custom_backdating_open")
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
	frappe.db.commit()
	try:
		_execute()
	finally:
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", was or 0)
		frappe.db.commit()


def _execute():
	data = data_mod.load()
	print("seeding Mutara from its tracker ({}, as of {})".format(data["source"], data["as_of"]))
	ensure_cost_center()
	ensure_fuel_store()
	ensure_items(data)
	ensure_feed_records(data)
	frappe.db.commit()
	ensure_opening_stock(data)
	frappe.db.commit()
	retire_demo()
	frappe.db.commit()
	ensure_herds(data)
	ensure_rations(data)
	frappe.db.commit()
	ensure_animals(data)
	ensure_counts(data)
	frappe.db.commit()
	ensure_labour(data)
	ensure_fuel(data)
	ensure_settings()
	frappe.db.commit()
	counts = {h: frappe.db.get_value("Herds", h, "number_of_animals")
	          for h in list(CATTLE_HERDS) + [g["herd"] for g in data["shoat_groups"]]}
	print("done: {}".format(counts))
