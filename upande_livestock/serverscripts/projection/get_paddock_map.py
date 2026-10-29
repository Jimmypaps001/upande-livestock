# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Paddock and pen outlines, coloured by the herd standing on each, with the rotation check."""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.common.timings import get_timing
from upande_livestock.serverscripts.projection import data, paddocks


def build():
	places = data.place_rows()
	kind = {p["warehouse"]: p["kind"] for p in places}
	shoats = data.by_number_herds()
	herds = []
	for h in data.herd_rows():
		heads = int(shoats[h["name"]]["head"]) if h["name"] in shoats else int(h["number_of_animals"] or 0)
		herds.append({"herd": h["name"], "herd_class": h["herd_class"], "paddock": h["paddock"], "heads": heads})
	live = [h for h in herds if h["heads"] > 0 or h["paddock"]]
	colours = paddocks.herd_colours([h["herd"] for h in live])
	placed = paddocks.place_herds(places, live)
	grazing = [h for h in live if h["herd_class"] != "Fattening" and kind.get(h["paddock"]) != "Pen"]
	paddock_count = sum(1 for p in places if p["kind"] == "Paddock")
	rotation = paddocks.rotation_check(paddock_count, len(grazing), get_timing("paddock_graze_days"),
	                                   get_timing("paddock_rest_days"))
	stock = data.feed_stock()
	grazing_names = {h["herd"] for h in grazing}
	out_places = []
	for p in placed:
		herd_rows = [dict(x, colour=colours[x["herd"]]) for x in p["herds"]]
		out_places.append({
			"warehouse": p["warehouse"], "label": p["label"], "kind": p["kind"], "area_ha": p["area_ha"],
			"geojson": p["geojson"], "state": p["state"], "heads": p["heads"], "head_per_ha": p["head_per_ha"],
			"herds": herd_rows, "colour": herd_rows[0]["colour"] if herd_rows else paddocks.RESTING,
			"feed_kg": round(flt(stock["paddock_kg"].get(p["warehouse"])), 1),
		})
	grazing_ha = sum(flt(p["area_ha"]) for p in places if p["kind"] == "Paddock")
	grazing_head = sum(h["heads"] for h in grazing)
	return {
		"places": out_places,
		"herds": [dict(h, colour=colours.get(h["herd"]), grazing=h["herd"] in grazing_names) for h in live],
		"unplaced": paddocks.unplaced(places, live),
		"rotation": dict(rotation, grazing_ha=round(grazing_ha, 2), grazing_head=grazing_head,
		                 head_per_ha=round(grazing_head / grazing_ha, 1) if grazing_ha else None),
		"resting": [p["label"] for p in out_places if p["state"] == "resting" and p["kind"] == "Paddock"],
	}


@frappe.whitelist()
def get_paddock_map() -> dict:
	guard_read("Herds")
	return build()
