#!/usr/bin/env python3
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Extract what the Mutara seeder needs from the farm's tracker spreadsheet.

    /mnt/data/code/frappe16-mutara/env/bin/python -I scripts/extract_mutara_tracker.py \
        "/mnt/data/code/mona/apps/upande_scp/apps/Updated Animal_Production_Tracker .xlsx"

Writes upande_livestock/demo/data/mutara_tracker.json, which is committed; the
spreadsheet is not. The seeder (upande_livestock/demo/seed_mutara_tracker.py)
reads only the JSON, so it runs without openpyxl and without the file.

Needs openpyxl and nothing from Frappe. Every judgement made on the sheet's
data is written into the JSON's `notes`, so a reader of the seeder can see it.

DATES. The sheet is typed day-first (13/7/26) but Excel turned every date whose
day was 12 or less into a real date read month-first: 4 January became 1 April.
A real date is therefore ambiguous: it is what Excel says, or the same two
numbers swapped. Rows are in time order, so each date is resolved to the
earliest reading that is not before the previous row and not more than
`MAX_STEP` days after it. Strings are read day-first unless only month-first
makes sense ("3/31/1026"); a year like 1026 or 2016 is a typo for 2026.
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta

import openpyxl

AS_OF = date(2026, 11, 11)      # the day this extract was taken: nothing in the sheet is later
FIRST_YEAR = 2025              # the tracker starts in November 2025
MAX_STEP = 45                   # days one row may move past the previous one
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "upande_livestock", "demo", "data",
                   "mutara_tracker.json")

# ---------------------------------------------------------------------------
# names: the sheet's word for a feed -> the Item the seeder makes
# ---------------------------------------------------------------------------

# Feed Rates spells two feeds wrong and calls one "Potatoes", which is already
# an Item on this site (a crop in Products); the feed is its own Item.
ITEM_FOR_RATE = {
	"Lucerne": "Lucerne", "Vines": "Vines", "Napier": "Napier", "Maize Silage": "Maize Silage", "Hay": "Hay",
	"Maize Grain": "Maize Grain", "Wheat Bran": "Wheat Bran", "Wheat Polland": "Wheat Pollard",
	"Sunflower": "Sunflower Cake", "Canola": "Canola", "Potatoes": "Feed Potatoes", "Mineral Salt": "Mineral Salt",
	"Limestone": "Limestone", "DCP": "DCP", "Mollasses": "Molasses", "Sorghum Silage": "Sorghum Silage",
	"Chopped Maize": "Chopped Maize", "Meat Boost": "Meat Boost", "Meat Grower": "Meat Grower",
	"Vital Nyama": "Vital Nyama", "Diamond V": "Diamond V", "Vital Dry": "Vital Dry", "Zincur": "Zincur",
}

# Ration-sheet and shoat-sheet words, lower-cased and stripped.
ITEM_FOR_INGREDIENT = {
	"hay": "Hay", "nappier": "Napier", "napier": "Napier", "maize grain": "Maize Grain", "maize": "Maize Grain",
	"molasses": "Molasses", "wheat bran": "Wheat Bran", "lucern": "Lucerne", "lucerne": "Lucerne",
	"silage maize": "Maize Silage", "maize silage": "Maize Silage", "silage": "Maize Silage",
	"vines": "Vines", "sunflower": "Sunflower Cake", "sunflower meal": "Sunflower Cake",
	"limestone": "Limestone", "lime": "Limestone", "dcp": "DCP", "canola": "Canola",
	"soyabean meal": "Soyabean Meal", "vital kondoo": "Vital Kondoo",
	# "Stocklick" is not on Feed Rates. The tracker's mineral at about 1 % of the ration (Aug-Sep 2026) is
	# Vital Nyama; Mineral Salt is barely used. See notes.
	"stocklick": "Vital Nyama",
}

# Per-head doses outside the 100 %. The "NB" box under the feedlot rations gives
# Diamond V 7 g, Meat boost 25-50 g, Meat grow 60 ml. The sheet's own arithmetic
# for Meat boost is 50 g a head (10.75 kg for 215 finishers), so 50 g.
DOSES = {
	"diamond v (yeast)": ("Diamond V", 7, "Gram"),
	"meat boost": ("Meat Boost", 50, "Gram"),
	"meat grow": ("Meat Grower", 60, "Millilitre"),
}

# Feed-lot ration sheet groups -> the herd the farm calls it
RATION_HERDS = {
	"finishers": "Finishers", "growers": "Growers", "starters/breeders": "Starters/Breeders",
	"quarantine": "Quarantine", "incalf": "In-calf", "heifers": "Heifers", "milking": "Lactating",
}

# Daily Feed Tracker "Animal Type" -> herd
TRACKER_HERDS = {
	"finishers": "Finishers", "growers": "Growers", "incalf": "In-calf", "lactating": "Lactating",
	"heifers": "Heifers", "starters": "Starters/Breeders", "breeder": "Starters/Breeders",
	"quaritine": "Quarantine", "quarantine": "Quarantine",
}

FEEDLOT_TABS = ["280-up Finishers RFID", "250-up growers 1 RFID", "250-down growers 2 RFID"]
NEW_STOCK_TAB = "New stock RFID"
FINISHER_MIN_KG = 280           # from the tab name "280-up Finishers RFID"
GROWER_MIN_KG = 150             # from the ration sheet, "GROWERS(150-279KGS)"


# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------


def _fix_year(y):
	if y < 100:
		y += 2000
	if y < FIRST_YEAR or y > AS_OF.year:      # 1026, 2016: typos for 2026
		return AS_OF.year
	return y


def _make(y, m, d):
	try:
		return date(_fix_year(y), m, d)
	except ValueError:
		return None


def candidates(value):
	"""Every date `value` can honestly be read as, most likely first."""
	out = []
	if isinstance(value, datetime):
		value = value.date()
	if isinstance(value, date):
		out = [_make(value.year, value.month, value.day), _make(value.year, value.day, value.month)]
	elif isinstance(value, str):
		parts = [p for p in re.split(r"[/.\-]", value.strip()) if p]
		if len(parts) == 3 and all(p.isdigit() for p in parts):
			a, b, y = (int(p) for p in parts)
			out = [_make(y, b, a), _make(y, a, b)]     # day-first, then month-first
	seen, res = set(), []
	for d in out:
		if d and d not in seen:
			seen.add(d)
			res.append(d)
	return res


def resolve(value, prev=None, lo=None, hi=AS_OF):
	"""The earliest reading of `value` in [lo, hi] that does not go back before `prev`
	and does not jump more than MAX_STEP days past it. None when nothing fits."""
	ok = []
	for d in candidates(value):
		if lo and d < lo:
			continue
		if hi and d > hi:
			continue
		if prev and (d < prev or (d - prev).days > MAX_STEP):
			continue
		ok.append(d)
	return min(ok) if ok else None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def num(v):
	if isinstance(v, (int, float)) and not isinstance(v, bool):
		return float(v)
	if isinstance(v, str):
		try:
			return float(v.strip())
		except ValueError:
			return None
	return None


def text(v):
	if v is None:
		return ""
	if isinstance(v, float) and v.is_integer():
		return str(int(v))
	return str(v).strip()


def rows_of(wb, name):
	return [list(r) + [None] * 40 for r in wb[name].iter_rows(values_only=True)]


# ---------------------------------------------------------------------------
# sheets
# ---------------------------------------------------------------------------


def feed_rates(wb, notes):
	feeds = []
	for r in rows_of(wb, "Feed Rates")[1:]:
		name, rate = text(r[0]), num(r[1])
		if not name or rate is None:
			continue
		item = ITEM_FOR_RATE.get(name)
		if not item:
			raise SystemExit("Feed Rates has a feed this script does not know: %r" % name)
		feeds.append({"item": item, "sheet_name": name, "rate": rate})
	notes.append("Feed Rates: 'Mollasses' and 'Wheat Polland' are named Molasses and Wheat Pollard; 'Sunflower' is "
	             "Sunflower Cake; 'Potatoes' is Feed Potatoes because Potatoes is already a crop Item.")
	return feeds


def feedlot_rations(wb, notes):
	rows = rows_of(wb, "Feed lot rations 2026")
	on = resolve(text(rows[0][0]).split()[0], lo=date(2026, 1, 1))
	out = []
	# the sheet is seven blocks side by side, four columns each: name | % | kg
	for col in range(0, 28, 4):
		label = text(rows[2][col])
		if not label:
			continue
		key = re.sub(r"\s*\(.*$", "", label).strip().lower()
		herd = RATION_HERDS.get(key)
		if not herd:
			raise SystemExit("Feed lot rations: unknown group %r" % label)
		animals = num(rows[1][col + 2])
		kg = num(rows[2][col + 2])
		lines, doses = [], []
		for r in rows[4:16]:
			name = text(r[col]).lower()
			if not name or name == "total":
				continue
			if name in DOSES:
				amount = num(r[col + 2]) or 0
				if amount > 0:
					item, per_head, uom = DOSES[name]
					doses.append({"item": item, "per_head": per_head, "uom": uom, "sheet_name": text(r[col])})
				continue
			pct = num(r[col + 1]) or 0
			if pct <= 0:
				continue
			item = ITEM_FOR_INGREDIENT.get(name)
			if not item:
				raise SystemExit("Feed lot rations: unknown ingredient %r" % name)
			lines.append({"item": item, "pct": round(pct, 6), "sheet_name": text(r[col])})
		total = round(sum(line["pct"] for line in lines), 6)
		if abs(total - 1) > 1e-6:
			raise SystemExit("%s: percentages add to %s, not 100 %%" % (herd, total))
		out.append({"herd": herd, "sheet_group": label, "date": str(on), "animals": int(animals or 0),
		            "kg_per_head": kg, "lines": lines, "doses": doses})
	notes.append("Feed lot rations: 'Stocklick' (1 %) is Vital Nyama, the mineral the Daily Feed Tracker feeds at "
	             "about 1 % of the ration; Feed Rates has no stock lick of its own.")
	notes.append("Feed lot rations: doses follow the NB box (Diamond V 7 g, Meat grow 60 ml a head); Meat boost is "
	             "50 g, the top of its 25-50 g range and what the sheet's own total (10.75 kg / 215) works out to. "
	             "A dose is given to a group only where the sheet feeds that additive to it.")
	return out


def shoats(wb, notes):
	rows = rows_of(wb, "Shoats ration 2026")
	on = resolve(rows[0][0], lo=date(2026, 1, 1))
	lines, groups = [], []
	for r in rows[2:11]:
		name, kg, rate = text(r[0]), num(r[1]), num(r[2])
		if name and kg:
			item = ITEM_FOR_INGREDIENT.get(name.lower())
			if not item:
				raise SystemExit("Shoats ration: unknown ingredient %r" % name)
			lines.append({"item": item, "kg": kg, "rate": rate, "sheet_name": name})
	for r in rows[1:9]:
		g, n, kg = text(r[7]), num(r[8]), num(r[9])
		m = re.match(r"group\s*(\d+)$", g.lower())
		if m and n:
			groups.append({"herd": "Shoat Group %s" % m.group(1), "animals": int(n), "kg_per_day": kg})
	batch = sum(line["kg"] for line in lines)
	notes.append("Shoats ration: the groups mix sheep and goats (Medicine Cost names ewes, rams and he goats in "
	             "one dosing) but a herd has one species; they are seeded as Sheep.")
	return ({"name": "Shoat Concentrate", "date": str(on), "batch_kg": batch, "lines": lines},
	        groups)


def daily_tracker(wb, notes):
	"""The latest row per group: its date, head and kg fed that day."""
	rows = rows_of(wb, "Daily Feed Tracker")
	prev, last, dropped = None, {}, 0
	for r in rows[1:]:
		group = text(r[1]).lower()
		if not group or r[0] is None:
			continue
		on = resolve(r[0], prev=prev, lo=date(2025, 11, 1))
		if not on:
			dropped += 1
			continue
		prev = on
		herd = TRACKER_HERDS.get(group)
		if herd is None:
			continue          # "Finisher 1" / "Finisher 2": a split that ended in June
		last[text(r[1])] = {"herd": herd, "date": str(on), "animals": int(num(r[27]) or 0),
		                    "kg_day": num(r[25])}
	latest = max(v["date"] for v in last.values())
	if dropped:
		notes.append("Daily Feed Tracker: %d rows have a date that fits nowhere in the sequence and were skipped."
		             % dropped)
	return {"date": latest, "groups": last}


def labour(wb, notes):
	rows = rows_of(wb, "Labour Cost")
	prev, out, dropped, dupes = None, {}, [], 0
	for r in rows[1:]:
		feedlot, herders = num(r[1]), num(r[4])
		if r[0] is None or not (feedlot or herders):
			continue
		on = resolve(r[0], prev=prev, lo=date(2025, 11, 1))
		if not on:
			dropped.append(text(r[0]) if not isinstance(r[0], datetime) else str(r[0].date()))
			continue
		prev = on
		if str(on) in out:
			dupes += 1
			continue
		lines = []
		if feedlot:
			lines.append({"category": "Feedlot workers", "workers": int(feedlot), "day_rate": num(r[2])})
		if herders:
			lines.append({"category": "Herders", "workers": int(herders), "day_rate": num(r[5])})
		out[str(on)] = lines
	if dropped:
		notes.append("Labour Cost: rows dated %s skipped (after the extract date or out of sequence)."
		             % ", ".join(dropped))
	if dupes:
		notes.append("Labour Cost: %d rows repeat the date before them; the first is kept." % dupes)
	return [{"date": d, "rows": out[d]} for d in sorted(out)]


def fuel(wb, notes):
	rows = rows_of(wb, "Fuel Cost")
	head = [text(c) for c in rows[0]]
	machines = {i: re.sub(r"\s*\(l\)\s*$", "", h).strip() for i, h in enumerate(head[1:7], start=1)}
	prev, out, rate = None, [], None
	for r in rows[1:]:
		if r[0] is None:
			continue
		on = resolve(r[0], prev=prev, lo=date(2026, 1, 1))
		if not on:
			continue
		prev = on
		rate = num(r[8]) or rate
		for i, machine in machines.items():
			litres = num(r[i])
			if litres:
				out.append({"date": str(on), "machine": machine, "litres": litres})
	notes.append("Fuel Cost: only the Mixer Wagon has litres; its cost per litre (%s KES) is given once." % rate)
	return out, rate


def _weighing_dates(row):
	"""The two weighing dates in a feedlot tab's header: early Oct and early Nov 2026."""
	return [resolve(row[2], lo=date(2026, 9, 1)), resolve(row[4], lo=date(2026, 9, 1))]


def animals(wb, notes):
	by_tag = {}
	in_tab_dupes = []
	for tab in FEEDLOT_TABS:
		rows = rows_of(wb, tab)
		dates = _weighing_dates(rows[1])
		for r in rows[2:]:
			tag = text(r[1])
			if not tag.startswith("982"):
				continue
			weights = [{"date": str(d), "kg": num(r[c])} for d, c in zip(dates, (2, 4)) if d and num(r[c])]
			if not weights:
				continue
			a = {"tag": tag, "old_tag": text(r[0]), "sheet": tab, "weights": weights}
			have = by_tag.get(tag)
			if have and have["sheet"] == tab:
				in_tab_dupes.append(tag)
				if len(weights) <= len(have["weights"]):
					continue
			by_tag[tag] = a
	rows = rows_of(wb, NEW_STOCK_TAB)
	where_when = text(rows[0][0])                         # "Rumuruti 17/10/26"
	m = re.match(r"(.*?)\s+(\S+)$", where_when)
	source, arrived = (m.group(1), resolve(m.group(2))) if m else (where_when, None)
	new_stock = 0
	for r in rows[2:]:
		tag = text(r[1])
		if not tag.startswith("982") or not num(r[2]):
			continue
		new_stock += 1
		w = {"date": str(arrived), "kg": num(r[2])}
		if tag in by_tag:            # since weighed in a feedlot tab: keep that herd, add the arrival weight
			by_tag[tag]["weights"].insert(0, w)
			by_tag[tag].update(acquired=str(arrived), cost=num(r[3]), source=source)
			continue
		by_tag[tag] = {"tag": tag, "old_tag": "", "sheet": NEW_STOCK_TAB, "weights": [w], "acquired": str(arrived),
		               "cost": num(r[3]), "source": source}
	for a in by_tag.values():
		latest = a["weights"][-1]["kg"]
		if a["sheet"] == NEW_STOCK_TAB:
			a["herd"] = "Quarantine"
		else:
			a["herd"] = "Finishers" if latest >= FINISHER_MIN_KG else "Growers"
	if in_tab_dupes:
		notes.append("RFID tabs: %s appear twice in one tab; the row with more weighings is kept."
		             % ", ".join(sorted(set(in_tab_dupes))))
	notes.append("RFID tabs: the farm's groups and the tab names disagree. Feed lot rations say Growers are "
	             "150-279 kg and Finishers above 280; the tabs split the growers at 250 (250-up / 250-down) and "
	             "hold %d animals against 217 Finishers and 173 Growers on the tracker. The bands are taken from "
	             "the tab names (Finishers from 280 kg) and the ration sheet (Growers from 150 kg); each tagged "
	             "animal goes to the band of its latest weight, which gives Finishers %d and Growers %d. The 250 "
	             "split is two weighing lists inside Growers, not a herd boundary."
	             % (sum(1 for a in by_tag.values() if a["sheet"] != NEW_STOCK_TAB),
	                sum(1 for a in by_tag.values() if a["herd"] == "Finishers"),
	                sum(1 for a in by_tag.values() if a["herd"] == "Growers")))
	notes.append("New stock RFID: %d animals bought at %s on %s go to Quarantine, at the cost the tab gives each; "
	             "the tab does not say their sex, and feedlot stock is seeded Male." % (new_stock, source, arrived))
	notes.append("Breeders and Calves data are not seeded as animals: neither has RFID tags or weights for the "
	             "cows, calf rows carry their dam's tag number, and together they list 63 of the 87 head the "
	             "tracker feeds in In-calf, Lactating and Heifers. Those three herds keep the tracker's head count.")
	return sorted(by_tag.values(), key=lambda a: (a["herd"], a["tag"]))


def herd_counts(tracker, rations, animal_rows, notes):
	"""What each cattle herd holds. Herds with tagged animals count them; the rest take the tracker."""
	tagged = {}
	for a in animal_rows:
		tagged[a["herd"]] = tagged.get(a["herd"], 0) + 1
	out = {}
	latest = tracker["date"]
	sheet = {r["herd"]: r["animals"] for r in rations}
	stale = []
	for herd in sheet:
		rows = [g for g in tracker["groups"].values() if g["herd"] == herd]
		row = max(rows, key=lambda g: g["date"]) if rows else None
		if herd in tagged:
			out[herd] = {"count": tagged[herd], "source": "tagged animals",
			             "tracker": row["animals"] if row and row["date"] == latest else None}
		elif row and row["date"] == latest:
			out[herd] = {"count": row["animals"], "source": "Daily Feed Tracker %s" % latest}
		else:
			out[herd] = {"count": 0, "source": "not on the tracker since %s" % (row["date"] if row else "-")}
			stale.append("%s (ration sheet: %d)" % (herd, sheet[herd]))
	if stale:
		notes.append("Daily Feed Tracker: on its latest day (%s) only Finishers, Growers, Incalf, Lactating and "
		             "Heifers are fed; %s have not been fed since August/September and are seeded with no head "
		             "beyond tagged animals." % (latest, ", ".join(stale)))
	return out


def main(path):
	wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
	notes = []
	feeds = feed_rates(wb, notes)
	rations = feedlot_rations(wb, notes)
	concentrate, shoat_groups = shoats(wb, notes)
	known = {f["item"] for f in feeds}
	for line in concentrate["lines"]:
		if line["item"] not in known:          # Soyabean Meal, Vital Kondoo: priced only on the shoat sheet
			feeds.append({"item": line["item"], "sheet_name": line["sheet_name"], "rate": line["rate"]})
			known.add(line["item"])
	tracker = daily_tracker(wb, notes)
	animal_rows = animals(wb, notes)
	fuel_rows, diesel_rate = fuel(wb, notes)
	data = {
		"source": os.path.basename(path),
		"as_of": str(AS_OF),
		"feeds": feeds,
		"rations": rations,
		"shoat_concentrate": concentrate,
		"shoat_groups": shoat_groups,
		"tracker_latest": tracker,
		"herd_counts": herd_counts(tracker, rations, animal_rows, notes),
		"animals": animal_rows,
		"labour": labour(wb, notes),
		"fuel": fuel_rows,
		"diesel_rate": diesel_rate,
		"notes": notes,
	}
	os.makedirs(os.path.dirname(OUT), exist_ok=True)
	with open(OUT, "w") as f:
		json.dump(data, f, indent=1, sort_keys=False)
		f.write("\n")
	print("wrote %s: %d feeds, %d rations, %d shoat groups, %d animals, %d labour days, %d fuel rows"
	      % (os.path.relpath(OUT), len(feeds), len(rations), len(shoat_groups), len(animal_rows),
	         len(data["labour"]), len(fuel_rows)))
	for n in notes:
		print(" - " + n)


if __name__ == "__main__":
	if len(sys.argv) != 2:
		raise SystemExit(__doc__)
	main(sys.argv[1])
