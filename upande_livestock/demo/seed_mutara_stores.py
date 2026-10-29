# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Mutara's feed and drug stores, its paddocks and feedlot pens, and where each herd stands.

    bench --site mutara.local execute upande_livestock.demo.seed_mutara_stores.run

Idempotent: every step looks before it writes, and opening stock is received only into a store
that holds none of that item. Development / demo sites only (it posts a Material Receipt).

* Stores, all under "Mutara - MUT": Feed Store, Drug Store, Mixing Store, Concentrate Store,
  Hay Store, Silo. The drug store the beef seed made ("Livestock Drug Store - MUT", for the A.I.
  straws) is renamed to "Drug Store - MUT" (stock follows the rename).
* Livestock Settings: the Mixing Store is the feed store (what the feeding run manufactures into
  and issues from, `custom_feed_wip_warehouse`); Feed, Concentrate, Hay Store and Silo are the
  Feed Source Warehouses; stock-posting event types default to the Drug Store.
* Opening stock of demo feeds: concentrate, hay, silage and minerals.
* Paddocks A1-A7 already exist (warehouse type Paddock, GeoJSON in custom_raw_geojson). Three
  feedlot pens (type Pen) are drawn next to them. Breeding and grazing herds are placed on
  paddocks, the three feedlot herds in the pens.
"""

import json

import frappe
from frappe.utils import add_days, flt, today

COMPANY = "Mutara"
FARM = "Mutara"
PARENT = "Mutara - MUT"

STORES = ["Feed Store", "Drug Store", "Mixing Store", "Concentrate Store", "Hay Store", "Silo"]
LEGACY_DRUG_STORE = "Livestock Drug Store"
FEED_SOURCES = ["Feed Store", "Concentrate Store", "Hay Store", "Silo"]
MIXING = "Mixing Store"

# item, store, kg on hand, uom, rate
OPENING = [
	("Mutara Beef Meal", "Concentrate Store", 30000, 55),
	("Mutara Boma Hay", "Hay Store", 45000, 18),
	("Mutara Maize Silage", "Silo", 70000, 9),
	("Mutara Mineral Lick", "Feed Store", 1500, 70),
]
EXTRA_ITEMS = {"Mutara Mineral Lick": 70}

PEN_GROUP = "Feedlot"
# Pens sit just east of Paddock A: (name, west lng, south lat, width deg, height deg)
PENS = [("Feedlot Pen 1", 36.6706, 0.0536), ("Feedlot Pen 2", 36.6706, 0.0541), ("Feedlot Pen 3", 36.6706, 0.0546)]
PEN_W, PEN_H = 0.00055, 0.00033

# herd -> place (paddocks A2 and A5 are left to rest)
PLACEMENT = {
	"Lactation Group 1": "Paddock A1",
	"Lactation Group 2": "Paddock A3",
	"Bulling Heifers": "Paddock A4",
	"Weaner Heifers": "Paddock A6",
	"Bull Reserve": "Paddock A7",
	"Starters": "Feedlot Pen 1",
	"Growers": "Feedlot Pen 2",
	"Finishers": "Feedlot Pen 3",
}
# A young herd grows; give the heifers a target gain so the feed projection grows them
HEIFER_TARGET = {"Bulling Heifers": 0.7}


def _log(m):
	print("  " + m)


def _abbr():
	return frappe.db.get_value("Company", COMPANY, "abbr")


def full(name):
	return "{} - {}".format(name, _abbr())


def ensure_warehouse_type(name):
	if not frappe.db.exists("Warehouse Type", name):
		frappe.get_doc({"doctype": "Warehouse Type", "name": name}).insert(ignore_permissions=True)
		_log("warehouse type " + name)


def ensure_warehouse(name, parent=PARENT, wtype=None, is_group=0, geojson=None):
	"""Create or tidy `name` (without the company suffix); returns the full name."""
	wh = full(name)
	if frappe.db.exists("Warehouse", wh):
		for field, want in (("parent_warehouse", parent), ("custom_farm", FARM)):
			if want and frappe.db.get_value("Warehouse", wh, field) != want:
				frappe.db.set_value("Warehouse", wh, field, want)
		return wh
	doc = frappe.get_doc({
		"doctype": "Warehouse", "warehouse_name": name, "company": COMPANY, "parent_warehouse": parent,
		"is_group": is_group, "warehouse_type": wtype, "custom_farm": FARM,
		"custom_raw_geojson": json.dumps(geojson) if geojson else None,
	}).insert(ignore_permissions=True)
	_log("warehouse " + doc.name)
	return doc.name


def rename_legacy_drug_store():
	old, new = full(LEGACY_DRUG_STORE), full("Drug Store")
	if not frappe.db.exists("Warehouse", old):
		return
	merge = bool(frappe.db.exists("Warehouse", new))
	frappe.rename_doc("Warehouse", old, new, force=True, merge=merge)
	if not merge:
		frappe.db.set_value("Warehouse", new, "warehouse_name", "Drug Store")
	_log("renamed {} -> {}{}".format(old, new, " (merged)" if merge else ""))


def ensure_stores():
	rename_legacy_drug_store()
	for s in STORES:
		ensure_warehouse(s)


def ensure_settings():
	settings = frappe.get_single("Livestock Settings")
	changed = False
	if not settings.custom_feed_wip_warehouse:
		settings.custom_feed_wip_warehouse = full(MIXING)
		changed = True
	have = {r.warehouse for r in settings.feed_source_warehouses}
	for s in FEED_SOURCES:
		if full(s) not in have:
			settings.append("feed_source_warehouses", {"warehouse": full(s)})
			changed = True
	if not settings.custom_feed_item_group and frappe.db.exists("Item Group", "DAIRY"):
		settings.custom_feed_item_group = "DAIRY"
		changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.save()
		_log("Livestock Settings: feed store {}, sources {}".format(
			settings.custom_feed_wip_warehouse, [r.warehouse for r in settings.feed_source_warehouses]))
	drug = full("Drug Store")
	fixed = 0
	for et in frappe.get_all("Livestock Event Type", filters={"posts_stock_entry": 1}, fields=["name", "default_store"]):
		if not et.default_store:
			frappe.db.set_value("Livestock Event Type", et.name, "default_store", drug)
			fixed += 1
	if fixed:
		_log("{} stock-posting event types default to {}".format(fixed, drug))


def ensure_items():
	# The beef seed's three feeds may predate the DAIRY group (the feed catalogue's group): file them there.
	for item in ("Mutara Beef Meal", "Mutara Boma Hay", "Mutara Maize Silage"):
		if frappe.db.exists("Item", item) and frappe.db.get_value("Item", item, "item_group") != "DAIRY":
			frappe.db.set_value("Item", item, "item_group", "DAIRY")
			_log("{} filed under DAIRY".format(item))
	for item, rate in EXTRA_ITEMS.items():
		if not frappe.db.exists("Item", item):
			frappe.get_doc({
				"doctype": "Item", "item_code": item, "item_name": item, "item_group": "DAIRY",
				"stock_uom": "Kilogram", "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0,
				"include_item_in_manufacturing": 0, "valuation_rate": rate, "standard_rate": rate,
			}).insert(ignore_permissions=True)
			_log("item " + item)


def ensure_opening_stock():
	rows = []
	for item, store, qty, rate in OPENING:
		wh = full(store)
		if not frappe.db.exists("Item", item):
			continue
		if flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": wh}, "actual_qty")) > 0:
			continue
		rows.append((item, wh, qty, rate))
	if not rows:
		return None
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = se.purpose = "Material Receipt"
	se.company = COMPANY
	se.set_posting_time = 1
	se.posting_date = add_days(today(), -300)       # predates every feeding run that draws on it
	se.remarks = "Mutara beef demo: opening feed stock"
	for item, wh, qty, rate in rows:
		se.append("items", {"item_code": item, "qty": qty, "t_warehouse": wh, "basic_rate": rate})
	se.insert(ignore_permissions=True)
	se.submit()
	_log("opening feed stock {} ({} lines)".format(se.name, len(rows)))
	return se.name


def pen_geojson(name, lng, lat):
	ring = [[lng, lat], [lng + PEN_W, lat], [lng + PEN_W, lat + PEN_H], [lng, lat + PEN_H], [lng, lat]]
	return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {
		"name": name, "area_ha": round(PEN_W * 111320 * PEN_H * 110574 / 10000, 4), "kind": "pen"},
		"geometry": {"type": "Polygon", "coordinates": [ring]}}]}


def ensure_pens():
	group = ensure_warehouse(PEN_GROUP, wtype="Pen", is_group=1)
	for name, lng, lat in PENS:
		wh = full(name)
		if frappe.db.exists("Warehouse", wh):
			if not frappe.db.get_value("Warehouse", wh, "custom_raw_geojson"):
				frappe.db.set_value("Warehouse", wh, "custom_raw_geojson", json.dumps(pen_geojson(name, lng, lat)))
			if frappe.db.get_value("Warehouse", wh, "warehouse_type") != "Pen":
				frappe.db.set_value("Warehouse", wh, "warehouse_type", "Pen")
			continue
		ensure_warehouse(name, parent=group, wtype="Pen", geojson=pen_geojson(name, lng, lat))


def place_herds():
	for herd, place in PLACEMENT.items():
		if not frappe.db.exists("Herds", herd):
			continue
		wh = full(place)
		if not frappe.db.exists("Warehouse", wh):
			continue
		if frappe.db.get_value("Herds", herd, "paddock") != wh:
			frappe.db.set_value("Herds", herd, "paddock", wh)
			_log("{} -> {}".format(herd, wh))
	for herd, adg in HEIFER_TARGET.items():
		if frappe.db.exists("Herds", herd) and not flt(frappe.db.get_value("Herds", herd, "target_adg_kg")):
			frappe.db.set_value("Herds", herd, "target_adg_kg", adg)
			_log("{} target gain {} kg/day".format(herd, adg))


def run():
	print("Mutara stores, paddocks and pens")
	ensure_warehouse_type("Pen")
	ensure_stores()
	ensure_items()
	ensure_settings()
	ensure_opening_stock()
	ensure_pens()
	place_herds()
	frappe.db.commit()
	print("done")
