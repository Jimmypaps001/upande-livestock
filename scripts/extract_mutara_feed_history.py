#!/usr/bin/env python3
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Extract a year of Mutara's feeding, as history, from the farm's tracker spreadsheet.

    /mnt/data/code/frappe16-mutara/env/bin/python -I scripts/extract_mutara_feed_history.py \
        "/mnt/data/code/mona/apps/upande_scp/apps/Updated Animal_Production_Tracker .xlsx"

Writes upande_livestock/demo/data/mutara_feed_history.json, which is committed;
the spreadsheet is not. demo/seed_mutara_feed_history.py reads only the JSON and
writes Livestock Feed History records from it.

Why a separate file from mutara_tracker.json: that one feeds the seeder that
builds the farm (items, herds, rations); this one is a year of the "Daily Feed
Tracker" sheet, kept as HISTORY WITHOUT STOCK. The feed was never received
into the system, so nothing here can become a stock entry; the cost is the
sheet's own "Feed Cost (KES)" for the row, and each line carries the "Feed
Rates" price only to show what the sheet priced it at.

The dates, the item names and the herd names are the main extractor's
(scripts/extract_mutara_tracker.py, loaded by path so the two never disagree).
Two pairs of sheet groups are one herd in the app: "Finisher 1"/"Finisher 2"
(a split of the finishers that ended in June) are Finishers, and "Starters" /
"Breeder" are Starters/Breeders. Where both halves are on the same day they are
added together — one record per herd and day — and the notes say how often.
The sheet also often lists "Finishers" (or "Breeder") twice on a day with
different head: two pens. The day's total row under them adds both, so they
are added here too.
"""

import importlib.util
import json
import os
import sys
from datetime import date

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "upande_livestock", "demo", "data", "mutara_feed_history.json")
SOURCE = "Tracker"

# Loaded by path: `python -I` does not put this directory on sys.path.
_spec = importlib.util.spec_from_file_location("extract_mutara_tracker", os.path.join(HERE, "extract_mutara_tracker.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

#: Sheet groups -> herd. The main extractor's, plus the finishers' two halves.
HERDS = dict(base.TRACKER_HERDS, **{"finisher 1": "Finishers", "finisher 2": "Finishers"})

#: The tracker's column headings that differ from their Feed Rates name.
COLUMN_RATE_NAME = {"Potatoes (Kgs)": "Potatoes"}

FIRST_COL, LAST_COL = 2, 24       # Lucerne (kg) .. Zincur
COL_KG, COL_COST, COL_ANIMALS = 25, 26, 27


def _rate_name(heading):
	h = base.text(heading)
	if h in COLUMN_RATE_NAME:
		return COLUMN_RATE_NAME[h]
	return h[:-len(" (kg)")] if h.endswith(" (kg)") else h


def columns(head):
	"""{column index: Item} for the 23 feed columns, failing loudly on a heading nobody mapped."""
	out = {}
	for i in range(FIRST_COL, LAST_COL + 1):
		name = _rate_name(head[i])
		item = base.ITEM_FOR_RATE.get(name)
		if not item:
			raise SystemExit("Daily Feed Tracker: feed column %r has no Item" % base.text(head[i]))
		out[i] = item
	return out


def rates(wb):
	return {base.ITEM_FOR_RATE[base.text(r[0])]: base.num(r[1])
	        for r in base.rows_of(wb, "Feed Rates")[1:] if base.text(r[0]) and base.num(r[1]) is not None}


def history(wb, notes):
	rows = base.rows_of(wb, "Daily Feed Tracker")
	cols = columns(rows[0])
	price = rates(wb)
	prev, dropped, merged, empty, cost_gap = None, [], 0, 0, 0
	unknown = set()
	records = {}
	for n, r in enumerate(rows[1:], start=2):
		group = base.text(r[1]).lower()
		if not group or r[0] is None:
			continue          # blank rows and the day's total row (no date, no group)
		on = base.resolve(r[0], prev=prev, lo=date(2025, 11, 1))
		if not on:
			dropped.append(n)
			continue
		prev = on
		herd = HERDS.get(group)
		if not herd:
			unknown.add(base.text(r[1]))
			continue
		items = {}
		for i, item in cols.items():
			kg = base.num(r[i]) or 0.0
			if kg > 0:
				items[item] = items.get(item, 0.0) + kg
		cost = base.num(r[COL_COST]) or 0.0
		head = int(base.num(r[COL_ANIMALS]) or 0)
		if not items and not cost:
			empty += 1
			continue
		key = (str(on), herd)
		rec = records.get(key)
		if rec is None:
			rec = records[key] = {"date": str(on), "herd": herd, "groups": [], "head_count": 0,
			                      "total_cost": 0.0, "items": {}}
		else:
			merged += 1
		rec["groups"].append(base.text(r[1]))
		rec["head_count"] += head
		rec["total_cost"] += cost
		for item, kg in items.items():
			rec["items"][item] = rec["items"].get(item, 0.0) + kg
	out = []
	for (_day, _herd), rec in sorted(records.items()):
		lines = [{"item": item, "qty_kg": round(kg, 3), "rate": price.get(item, 0.0),
		          "amount": round(kg * price.get(item, 0.0), 2)}
		         for item, kg in rec["items"].items()]
		priced = sum(line["amount"] for line in lines)
		if abs(priced - rec["total_cost"]) > max(1.0, 0.01 * rec["total_cost"]):
			cost_gap += 1
		out.append({"date": rec["date"], "herd": rec["herd"], "groups": rec["groups"],
		            "head_count": rec["head_count"], "total_kg": round(sum(rec["items"].values()), 3),
		            "total_cost": round(rec["total_cost"], 2), "lines": lines})
	if dropped:
		notes.append("Daily Feed Tracker: rows %s have a date that fits nowhere in the sequence and were skipped."
		             % ", ".join(map(str, dropped)))
	if unknown:
		raise SystemExit("Daily Feed Tracker: groups with no herd: %s" % ", ".join(sorted(unknown)))
	if empty:
		notes.append("Daily Feed Tracker: %d rows feed nothing and cost nothing; not kept." % empty)
	notes.append("'Finisher 1'/'Finisher 2' are Finishers and 'Starters'/'Breeder' are Starters/Breeders; %d "
	             "rows shared a day and herd with another and were added into it (kg, cost and head). Most are two "
	             "'Finishers' rows on one day with different head (two pens); the sheet's own day-total row adds "
	             "them the same way." % merged)
	notes.append("Cost is the sheet's own Feed Cost (KES) per row. Each line's rate is the Feed Rates price, "
	             "shown for reference; on %d records the lines priced that way differ from the sheet's cost by "
	             "more than 1 %%, and the sheet's figure is kept." % cost_gap)
	return out


def dumps(data):
	"""JSON with one record per line: a year of days stays a diffable file, not 50,000 lines."""
	head = {k: v for k, v in data.items() if k != "records"}
	body = ",\n".join("  " + json.dumps(r, separators=(",", ":")) for r in data["records"])
	text = json.dumps(head, indent=1)[:-2]
	return text + ',\n "records": [\n' + body + "\n ]\n}\n"


def main(path):
	wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
	notes = []
	recs = history(wb, notes)
	data = {
		"source": os.path.basename(path),
		"sheet": "Daily Feed Tracker",
		"as_of": str(base.AS_OF),
		"source_label": SOURCE,
		"records": recs,
		"notes": notes,
	}
	with open(OUT, "w") as f:
		f.write(dumps(data))
	herds = {}
	for r in recs:
		herds[r["herd"]] = herds.get(r["herd"], 0) + 1
	print("wrote %s: %d records, %s to %s, %s" % (os.path.relpath(OUT), len(recs), recs[0]["date"],
	                                              recs[-1]["date"], herds))
	for n in notes:
		print(" - " + n)


if __name__ == "__main__":
	if len(sys.argv) != 2:
		raise SystemExit(__doc__)
	main(sys.argv[1])
