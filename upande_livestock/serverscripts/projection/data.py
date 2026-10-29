# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Reads for the feed projection and the paddock map. The maths is in engine.py and
paddocks.py (pure); this is the part that talks to the database."""

import json

import frappe
from frappe.utils import add_days, flt, getdate

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.calf_separation import is_suckling
from upande_livestock.serverscripts.common.gain import weights_for_many
from upande_livestock.serverscripts.common.timings import FLOAT_TIMING_DEFAULTS, get_timing, read_setting
from upande_livestock.serverscripts.common.weight_bands import fattening_bands
from upande_livestock.serverscripts.forecast import data as forecast_data
from upande_livestock.serverscripts.projection import engine, paddocks

KG_UOMS = ("kg", "kilogram", "kilograms")
PLACE_TYPES = ("Paddock", "Pen")


def float_setting(key):
	value = read_setting(key)
	if value in (None, ""):
		return FLOAT_TIMING_DEFAULTS[key]
	return flt(value)


def settings():
	return {
		"dm_intake_pct": float_setting("dm_intake_pct"),
		"adg_min_kg": float_setting("adg_min_kg"),
		"adg_max_kg": float_setting("adg_max_kg"),
		"min_weighings": get_timing("adg_min_weighings"),
		"min_span_days": get_timing("adg_min_span_days"),
		"exit_weight_kg": forecast_data.exit_weight_setting(),
	}


def by_number_herds():
	"""{herd: row} for the by-number (sheep and goat) herds; empty where the Shoats module is absent."""
	try:
		from upande_livestock.serverscripts.common.shoats import shoat_herd_numbers
	except ImportError:
		return {}
	return {r["herd"]: r for r in shoat_herd_numbers()}


def herd_rows(only=None):
	filters = {"name": only} if only else {}
	return frappe.get_all(
		"Herds", filters=filters, order_by="name asc",
		fields=["name", "herd_class", "number_of_animals", "target_adg_kg", "paddock", "min_weight_kg", "max_weight_kg"])


def herd_grows(herd):
	"""A herd gains weight in the projection when it is a feedlot herd or has a target gain."""
	return herd["herd_class"] == "Fattening" or flt(herd["target_adg_kg"]) > 0


def animals_and_herds(on, only=None):
	"""(engine animals, herd summaries) for today. See `engine.project` for the animal shape."""
	cfg = settings()
	bands = fattening_bands()
	shoats = by_number_herds()
	herds = herd_rows(only)
	individual = [h for h in herds if h["name"] not in shoats]
	rows = frappe.get_all(
		"Animal",
		filters={"current_herd": ["in", [h["name"] for h in individual] or [""]], "disabled": 0,
		         "docstatus": ["!=", 2], "status": ["not in", list(RETIRED_STATUSES)]},
		fields=["name", "current_herd", "date_of_birth"], limit=20000)
	history = weights_for_many([r.name for r in rows], birth=False)
	by_herd = {}
	for r in rows:
		by_herd.setdefault(r.current_herd, []).append(r)

	animals, summaries = [], {}
	for h in individual:
		name = h["name"]
		grows = herd_grows(h)
		target = flt(h["target_adg_kg"]) or None
		exit_kg = forecast_data.exit_weight_for_herd(name, bands) if h["herd_class"] == "Fattening" else None
		members = by_herd.get(name, [])
		calves = [m for m in members if is_suckling(m.date_of_birth, on)]
		fed = [m for m in members if not is_suckling(m.date_of_birth, on)]
		weighed = [m for m in fed if history[m.name]]
		avg = (sum(history[m.name][-1][1] for m in weighed) / len(weighed)) if weighed else None
		estimated = 0
		for m in fed:
			pts = history[m.name]
			measured = engine.measured_adg(pts, cfg["min_weighings"], cfg["min_span_days"]) if pts else None
			adg = engine.adg_scenarios(measured, target, grows, cfg["adg_min_kg"], cfg["adg_max_kg"])
			if pts:
				date_, kg = pts[-1]
				kg_today = kg + adg["expected"] * max(0, (getdate(on) - date_).days)
			elif avg is not None:
				kg_today, estimated = avg, estimated + 1
			else:
				continue
			animals.append({"id": m.name, "herd": name, "kg": kg_today, "adg": adg, "exit_kg": exit_kg})
		summaries[name] = {
			"herd": name, "herd_class": h["herd_class"], "paddock": h["paddock"], "counting": "Individual",
			"head": len(members), "calves": len(calves), "fed_heads": len(fed), "weighed": len(weighed),
			"estimated": estimated, "unweighed": len(fed) - len(weighed) - (estimated if avg is not None else 0),
			"grows": grows, "target_adg_kg": target,
		}
	for h in herds:
		row = shoats.get(h["name"])
		if not row:
			continue
		live = flt(row.get("live_weight_kg"))
		head = int(row.get("head") or 0)
		grows = herd_grows(h)
		target = flt(h["target_adg_kg"]) or None
		per_head = engine.adg_scenarios(None, target, grows, cfg["adg_min_kg"], cfg["adg_max_kg"])
		lump = {k: (v * head if k != "source" else v) for k, v in per_head.items()}
		if live > 0:
			animals.append({"id": h["name"], "herd": h["name"], "kg": live, "adg": lump, "exit_kg": None})
		summaries[h["name"]] = {
			"herd": h["name"], "herd_class": h["herd_class"], "paddock": h["paddock"], "counting": "By number",
			"species": row.get("species"), "head": head, "calves": 0, "fed_heads": head, "weighed": 0,
			"estimated": 0, "unweighed": 0 if live > 0 else head, "grows": grows, "target_adg_kg": target,
			"weight_basis": row.get("weight_basis"),
		}
	return animals, summaries


def feed_warehouses():
	"""Where feed is held: the configured source stores, the feed (mixing) store, and every herd's paddock or pen."""
	names = []
	for r in frappe.get_all("Livestock Feed Warehouse", filters={"parenttype": "Livestock Settings"},
	                        fields=["warehouse"], order_by="idx asc"):
		if r.warehouse:
			names.append(r.warehouse)
	store = frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse")
	if store and store not in names:
		names.append(store)
	central = list(names)
	for p in frappe.get_all("Herds", filters={"paddock": ["is", "set"]}, pluck="paddock"):
		if p not in names:
			names.append(p)
	return central, names


def feed_stock():
	"""{central_kg, by_warehouse: {wh: kg}, items: [...], uncounted: [...]} of feed items on hand.

	Feed is every item in the farm's feed item group held in those warehouses. Quantities are kilograms:
	an item stocked in another unit counts through its weight per unit when it has one, else is listed
	as uncounted. No moisture correction: a kilogram in store is a kilogram of intake."""
	from upande_livestock.serverscripts.feeding.feed_in_store import feed_item_group

	central, names = feed_warehouses()
	if not names:
		return {"central_kg": 0.0, "paddock_kg": {}, "total_kg": 0.0, "items": [], "uncounted": [], "warehouses": []}
	rows = frappe.db.sql(
		"""SELECT i.name AS item_code, i.item_name, i.stock_uom AS uom, i.weight_per_unit, i.weight_uom,
		          b.warehouse, b.actual_qty AS qty
		   FROM `tabBin` b JOIN `tabItem` i ON i.name = b.item_code
		   WHERE b.warehouse IN %(wh)s AND b.actual_qty > 0 AND IFNULL(i.disabled, 0) = 0
		     AND i.item_group = %(grp)s""",
		{"wh": tuple(names), "grp": feed_item_group()}, as_dict=True)
	items, uncounted = [], []
	by_wh = {}
	for r in rows:
		if (r.uom or "").lower() in KG_UOMS:
			kg = flt(r.qty)
		elif flt(r.weight_per_unit) > 0 and (r.weight_uom or "").lower() in KG_UOMS:
			kg = flt(r.qty) * flt(r.weight_per_unit)
		else:
			uncounted.append({"item_code": r.item_code, "item_name": r.item_name or r.item_code,
			                  "qty": flt(r.qty), "uom": r.uom, "warehouse": r.warehouse})
			continue
		by_wh[r.warehouse] = by_wh.get(r.warehouse, 0.0) + kg
		items.append({"item_code": r.item_code, "item_name": r.item_name or r.item_code, "kg": kg,
		              "warehouse": r.warehouse})
	items.sort(key=lambda x: -x["kg"])
	central_kg = sum(v for k, v in by_wh.items() if k in central)
	return {
		"central_kg": central_kg,
		"paddock_kg": {k: v for k, v in by_wh.items() if k not in central},
		"total_kg": sum(by_wh.values()),
		"items": items, "uncounted": uncounted,
		"warehouses": [{"warehouse": k, "kg": v, "central": k in central} for k, v in sorted(by_wh.items())],
	}


def place_rows():
	"""Every paddock and pen: {warehouse, label, kind, area_ha, geojson|None}."""
	rows = frappe.get_all(
		"Warehouse", filters={"warehouse_type": ["in", list(PLACE_TYPES)], "is_group": 0, "disabled": 0},
		fields=["name", "warehouse_name", "warehouse_type", "custom_raw_geojson"], order_by="name asc")
	out = []
	for r in rows:
		gj = None
		if r.custom_raw_geojson:
			try:
				gj = json.loads(r.custom_raw_geojson)
			except ValueError:
				gj = None
		out.append({"warehouse": r.name, "label": r.warehouse_name or r.name, "kind": r.warehouse_type,
		            "area_ha": paddocks.area_ha(gj), "geojson": gj})
	out.sort(key=lambda p: (p["kind"] != "Paddock", _natural(p["label"])))
	return out


def _natural(s):
	import re

	return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]
