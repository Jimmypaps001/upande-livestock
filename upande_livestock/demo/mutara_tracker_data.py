# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Mutara's tracker data, as the seeder uses it. Pure Python: no Frappe here, so
the arithmetic is testable without a site.

The JSON is written by scripts/extract_mutara_tracker.py from the farm's
spreadsheet and committed; the spreadsheet is not.
"""

import json
import math
import os

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mutara_tracker.json")

#: A dose is typed in grams or millilitres; the Item is stocked in kilograms or litres.
DOSE_STOCK_UOM = {"Gram": "Kilogram", "Millilitre": "Litre"}
DOSE_FACTOR = {"Gram": 0.001, "Millilitre": 0.001}

#: Decimal places a ration line keeps, in the stock UOM (a gram of a kilogram item).
QTY_PLACES = 3


def load(path=DATA_PATH):
	with open(path) as f:
		return json.load(f)


def ration_lines(ration):
	"""One head's day, as BOM lines in each item's stock UOM.

	The sheet gives kilograms a head a day and each ingredient as a share of
	it; a dose (Diamond V 7 g, Meat Grower 60 ml) is per head and outside the
	100 %. 14 kg at 8 % hay is 1.12 kg of hay; 7 g of Diamond V is 0.007 kg.
	"""
	kg = float(ration["kg_per_head"])
	out = []
	for line in ration["lines"]:
		out.append({"item_code": line["item"], "qty": round(kg * float(line["pct"]), QTY_PLACES)})
	for dose in ration.get("doses") or []:
		out.append({"item_code": dose["item"],
		            "qty": round(float(dose["per_head"]) * DOSE_FACTOR[dose["uom"]], QTY_PLACES)})
	return [line for line in out if line["qty"] > 0]


def shoat_per_head(group):
	"""Kilograms of the made batch one animal of a shoat group gets a day."""
	return round(float(group["kg_per_day"]) / int(group["animals"]), QTY_PLACES)


def dose_uoms(data):
	"""{item: (stock_uom, dose_uom)} for the items dosed per head."""
	out = {}
	for ration in data["rations"]:
		for dose in ration.get("doses") or []:
			out[dose["item"]] = (DOSE_STOCK_UOM[dose["uom"]], dose["uom"])
	return out


def head_of(data, herd):
	"""The head a herd is fed for: its tagged animals, or the tracker's count."""
	row = data["herd_counts"].get(herd)
	if row:
		return int(row["count"])
	for g in data["shoat_groups"]:
		if g["herd"] == herd:
			return int(g["animals"])
	return 0


def daily_need(data):
	"""{item: stock-UOM quantity a day} the herds eat at today's rations and head."""
	need = {}
	for ration in data["rations"]:
		head = head_of(data, ration["herd"])
		for line in ration_lines(ration):
			need[line["item_code"]] = need.get(line["item_code"], 0.0) + line["qty"] * head
	conc = data["shoat_concentrate"]
	batch = float(conc["batch_kg"])
	made = sum(float(g["kg_per_day"]) for g in data["shoat_groups"])
	for line in conc["lines"]:
		need[line["item"]] = need.get(line["item"], 0.0) + made * float(line["kg"]) / batch
	return need


def opening_quantities(data, days=30, step=100, floor=100):
	"""What to receive once so every feed has stock and a valuation: `days` of
	today's need, rounded up to `step`; a feed nothing eats today gets `floor`."""
	need = daily_need(data)
	out = {}
	for feed in data["feeds"]:
		qty = need.get(feed["item"], 0.0) * days
		out[feed["item"]] = max(floor, int(math.ceil(qty / step)) * step)
	return out
