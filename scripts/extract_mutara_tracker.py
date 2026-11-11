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


MONTHS = {m: i for i, m in enumerate(
	["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


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
		parts = [p for p in re.split(r"[/.\-]", value.strip().strip("()")) if p]
		worded = re.match(r"^\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})\s*$", value)
		if len(parts) == 3 and all(p.isdigit() for p in parts):
			a, b, y = (int(p) for p in parts)
			out = [_make(y, b, a), _make(y, a, b)]     # day-first, then month-first
		elif worded and worded.group(2)[:3].lower() in MONTHS:     # "26th June 2026": no ambiguity
			out = [_make(int(worded.group(3)), MONTHS[worded.group(2)[:3].lower()], int(worded.group(1)))]
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
	for herd in list(sheet) + sorted(set(tagged) - set(sheet)):
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


# ---------------------------------------------------------------------------
# history: breeders and calves, sales, old weighing sheets, health
# ---------------------------------------------------------------------------

CALF_HERD = "Calves"
#: Breeders "Pregnancy Status" -> (herd, repro_status). A dry cow is neither milking nor recorded
#: pregnant; the farm has three cow herds and none for dry cows, which are fed with the in-calf ones.
COW_PLACE = {"pregnant": ("In-calf", "Pregnant"), "dry": ("In-calf", "Open"), "lactating": ("Lactating", "Open"),
             "not pregnant": ("Heifers", "Heifer")}
RFID_PREFIX = "982 091086"
#: Steers sold types two RFIDs wrong; the Finishers sold tab lists the RFIDs sold in Oct-Nov in full, and
#: each typo can only be one of them.
RFID_TYPOS = {"401137": "140137"}
#: Livestock Settings' calf_separation_age_days on mutara.local: a calf younger than this is with its mother.
SUCKLING_DAYS = 210
CARCASS_RATE_FROM = 450 # KES a kg above which a sale is priced on the carcass, not the live animal
MIN_WEIGH_GAP = 14      # a monthly weighing header is at least two weeks after the one before it
MIN_KG = 80             # below this a number in a weighing column is a gain, not a weight
MAX_ADG = 2.5           # kg a day: a match implying more is a different animal with the same tag
MAX_LOSS = 15           # kg an animal may weigh less at its next weighing and still be itself
SALE_SHEETS = ("Steers sold 2026", "Moyale sold", "Breeders sold")
OLD_SHEETS = ("Old New stock", "Old finishers", "Old growers ", "Finishers sold ")


def sa_of(value):
	"""An SA ear tag number: Breeders writes 913, Calves data the 13 0913 printed on the tag."""
	n = num(value)
	if not n:
		return None
	n = int(n)
	return n - 130000 if n > 130000 else n


def calf_sexes(value):
	"""The sexes in a 'Number of Calves Produced' cell, None where it does not say.

	'2(Male)' -> [Male, Male]; '1(male), 1(Female)' and '2 (male,Female)' -> [Male, Female];
	'1' -> [None]; 0 -> [].
	"""
	s = text(value).lower()
	nums = [int(n) for n in re.findall(r"\d+", s)]
	words = ["Female" if w == "female" else "Male" for w in re.findall(r"female|male", s)]
	total = sum(nums)
	if not words:
		return [None] * total
	if len(nums) == len(words):
		return [w for n, w in zip(nums, words) for _ in range(n)]
	if len(nums) == 1 and len(words) == 1:
		return words * nums[0]
	if len(nums) == 1 and len(words) == nums[0]:
		return words
	return [None] * total


def as_typed(value):
	"""A one-off date (a vaccination, a sale): Excel's own reading first, swapped only when that is
	later than the extract, and a year earlier when both are (25/12/26 for Christmas 2025).

	Unlike a weighing column there is no sequence to resolve it against. Medicine Cost lists the
	CBPP campaign after 22 July, so Excel's 6 September stands rather than 9 June.
	"""
	found = candidates(_date_text(value))
	for d in found:
		if d <= AS_OF:
			return d
	for d in found:
		try:
			earlier = d.replace(year=d.year - 1)
		except ValueError:
			continue
		if earlier <= AS_OF:
			return earlier
	return None


def _date_text(value):
	"""'KG(18/12/25)' and '(4/2/26)' carry a date inside other text."""
	if isinstance(value, str):
		m = re.search(r"\d{1,2}[/.]\d{1,2}[/.]\d{2,4}", value)
		if m:
			return m.group(0)
	return value


def header_dates(cells, lo):
	"""{column: date} for a row of monthly weighing headers, resolved in order.

	Each header is read as the earliest reading at least MIN_WEIGH_GAP days after the one before:
	two headers can both say 3 February (3/2 and 2/3 as Excel stored them), and the second is 2 March.
	"""
	out, prev = {}, None
	for col, value in cells:
		value = _date_text(value)
		if value is None or not candidates(value):
			continue
		d = resolve(value, prev=prev, lo=(prev + timedelta(days=MIN_WEIGH_GAP)) if prev else lo)
		if d:
			out[col] = d
			prev = d
	return out


def row_weights(row, dates, until=None):
	"""Weighings on a row: a number of MIN_KG or more under a dated header, not after `until`."""
	out = []
	for col, d in sorted(dates.items(), key=lambda x: x[1]):
		kg = num(row[col])
		if kg and kg >= MIN_KG and (not until or d <= until):
			out.append({"date": str(d), "kg": kg})
	return out


def _strip0(s):
	m = re.match(r"^0*(\d+)([A-Z]?)$", s)
	return (m.group(1) + m.group(2)) if m else s


KEY_PREFIX = {"MOL": "MOL", "M0L": "MOL", "R": "MOL", "IMANI": "IMANI", "KIFARU": "KIFARU", "KF": "KIFARU",
              "LE": "LE", "LMN": "LMN"}


def tag_keys(raw, plain="BARE"):
	"""The (series, number) keys an old tag can be matched by.

	The farm re-tags: '74/ R 769' is old tag 74, now MOL769 ('R' is the re-tag), which the RFID tabs
	write as MOL769; '102/840' is the same without the R. A bare first number is the original tag,
	which the RFID tabs write bare ('4'); Old New stock numbers are already MOL tags (`plain='MOL'`).
	KF is Kifaru, the seller the RFID tabs spell out. Leading zeros and a weight in brackets are dropped.
	"""
	s = re.sub(r"\(.*?\)", " ", text(raw).upper())
	keys = []
	for i, tok in enumerate(t for t in s.split("/") if t.strip()):
		tok = re.sub(r"[\s\-]", "", tok)
		m = re.match(r"^(MOLF\d|MOL|M0L|IMANI|KIFARU|KF|LE|LMN|R)(\w+)$", tok)
		if m:
			body = m.group(2).replace("O", "0") if m.group(1) in ("MOL", "M0L") else m.group(2)
			keys.append((KEY_PREFIX.get(m.group(1), m.group(1)), _strip0(body)))
		elif re.match(r"^\d+[A-Z]?$", tok):
			keys.append((plain if i == 0 else "MOL", _strip0(tok)))
		elif tok:
			keys.append(("NAME", tok))
	return keys


def plausible(after, last):
	"""Can an animal weighing `last` ({date, kg}) be the one weighing `after` later?"""
	if not after or not last:
		return False
	days = (date.fromisoformat(after["date"]) - date.fromisoformat(last["date"])).days
	if days <= 0:
		return False
	gain = after["kg"] - last["kg"]
	return gain >= -MAX_LOSS and gain <= MAX_ADG * days


def consistent(weights):
	"""Do these weighings, from different sheets, belong to one animal? Two on one day agree within
	MAX_LOSS; each later one can follow the one before (plausible)."""
	ws = sorted(weights, key=lambda w: w["date"])
	for a, b in zip(ws, ws[1:]):
		if a["date"] == b["date"]:
			if abs(a["kg"] - b["kg"]) > MAX_LOSS:
				return False
		elif not plausible(b, a):
			return False
	return True


def _id_part(tag):
	return re.sub(r"[^A-Za-z0-9]+", "-", tag).strip("-").upper()


def _unique(ids, want):
	n, got = 1, want
	while got in ids:
		n += 1
		got = "%s-%d" % (want, n)
	ids.add(got)
	return got


# --- breeders and calves -----------------------------------------------------


def breeders(wb, notes):
	"""The cows, heifers and calves on Breeders, joined with Calves data. See the notes for every call."""
	rows = rows_of(wb, "Breeders")
	cows, young, section, skipped = [], [], "cows", []
	for r in rows[1:]:
		if text(r[0]).lower() == "calves":
			section = "young"
			continue
		if r[0] is None:
			continue
		if section == "cows":
			cows.append(_cow(r))
		elif text(r[2]):
			young.append(_young(r))
		else:
			skipped.append(text(r[0]))
	by_sa = {c["sa"]: c for c in cows if c["sa"]}
	by_tag = {c["old_tag"]: c for c in cows}
	for y in young:
		dam = by_sa.get(y.pop("dam_sa")) or by_tag.get(y["dam_tag"])
		y["dam"] = dam["id"] if dam else None
	calves_data(wb, young, by_sa, by_tag, notes)
	for y in young:
		if y["category"] == "breeding bull":
			y["sex"] = "Male"
	_sex_from_dams(cows, young, notes)
	moved = []
	for c in cows:
		mine = [y for y in young if y["dam"] == c["id"] and y["category"] != "breeding bull"]
		dobs = [y["date_of_birth"] for y in mine if y["date_of_birth"]]
		c["last_calving_date"] = max(dobs) if dobs else None
		c["parity"] = max(c["parity"], len(mine))
		calved = c["last_calving_date"]
		suckling = calved and (AS_OF - date.fromisoformat(calved)).days < SUCKLING_DAYS
		if suckling and c["herd"] != "Lactating":
			moved.append("%s (calved %s)" % (c["old_tag"], c["last_calving_date"]))
			c["remarks"] += "; calved %s (Calves data), so with the lactating cows" % c["last_calving_date"]
			c.update(herd="Lactating", repro_status="Open")
	if moved:
		notes.append("Breeders: %s are 'Pregnant' on Breeders but calved since (Calves data); a cow with a calf "
		             "under the %d-day separation age is suckling it, so they go to Lactating, repro status Open."
		             % (", ".join(moved), SUCKLING_DAYS))
	for y in young:
		if not y["dam"] and y["dam_tag"] and "not on Breeders" not in y["remarks"]:
			y["remarks"] += "; dam %s is not on Breeders" % y["dam_tag"]
	for y in young:
		if y["category"] == "breeding bull":
			y.update(herd="Lactating", repro_status="Bull", sex="Male")
		else:
			y.update(herd=CALF_HERD, repro_status="Calf")
		y["id"] = "SA-%d" % y["sa"] if y["sa"] else "CALF-" + _id_part(y["label"])
		if not y["burn_name"]:
			y["burn_name"] = y["label"] if re.search(r"[A-Z]", y["label"]) or len(y["label"]) == 6 \
				else "calf of " + y["label"]
	ids = [a["id"] for a in cows + young]
	if len(ids) != len(set(ids)):
		raise SystemExit("Breeders: duplicate ids %s" % sorted({i for i in ids if ids.count(i) > 1}))
	if skipped:
		notes.append("Breeders: calf rows %s have no category and nothing else; skipped." % ", ".join(skipped))
	counts = {}
	for a in cows + young:
		counts[a["herd"]] = counts.get(a["herd"], 0) + 1
	notes.append(
		"Breeders and Calves data are seeded as animals: %d cows and heifers, %d calves, weaners and a bull. "
		"The ID is the SA ear tag ('SA-913'; Calves data's 130913 is the same tag) and the old tag is the burn "
		"name; a cow with no SA tag is 'TAG-<old tag>' and a calf with none 'CALF-<label>', the label being the "
		"farm's dam-tag-and-letter ('2721A'). Pregnant cows go to In-calf, lactating ones to Lactating, the "
		"three dry cows (they calved in March and are neither milking nor recorded pregnant) to In-calf, and "
		"the not-pregnant heifers to Heifers. Calves and weaners go to a new Calves herd (class Calf, a "
		"Livestock Settings calf herd); the separation-due list then asks for the weaners to be moved. The "
		"breeding bull runs with the Lactating cows. Herds: %s."
		% (len(cows), len(young), ", ".join("%s %d" % kv for kv in sorted(counts.items()))))
	notes.append(
		"Breeders: no cow has a breed, date of birth, arrival or source, and no pregnant cow has an expected "
		"calving date or a diagnosis date, so no Pregnancy Diagnosis events are made: repro_status says "
		"Pregnant and nothing more. Parity is the 'Number of Calves Produced'; the last calving date is her "
		"youngest calf's birth date. Heifer weights have no date and go in the remarks, not as weighings. "
		"The 'Sire Tag No.' column under Calves holds the dam's SA tag, and is read as that.")
	return cows + young


def _cow(r):
	old, sa = text(r[0]), sa_of(r[1])
	category = text(r[2]).lower()
	status = text(r[10]).lower()
	herd, repro = COW_PLACE.get(status, ("Heifers", "Heifer") if category == "heifer" else ("Lactating", "Open"))
	weight = num(r[3])
	vacc = [(as_typed(r[c]), text(r[c + 1])) for c in (20, 22) if r[c] is not None and text(r[c + 1])]
	sexes = calf_sexes(r[12])
	return {
		"id": "SA-%d" % sa if sa else "TAG-" + _id_part(old), "sa": sa, "old_tag": old, "burn_name": old,
		"book_number": None, "label": old, "sex": "Female", "category": category, "herd": herd,
		"repro_status": repro, "parity": len(sexes), "calf_sexes": sexes, "date_of_birth": None, "dam": None,
		"dam_tag": None, "origin": None,
		"remarks": "Breeders: %s, %s%s" % (category, text(r[10]) or "status not given",
		                                    "; weighed %s kg (no date)" % weight if weight else ""),
		"vaccinations": [{"date": str(d), "name": n} for d, n in vacc if d],
	}


def _young(r):
	raw = text(r[0])
	label, _, book = raw.partition("/")
	label = label.strip().upper()
	book = book.strip()
	born = r[5]
	dob, year_only = None, None
	if isinstance(born, (int, float)):
		year_only = int(born)
	else:
		dob = resolve(born, lo=date(2024, 1, 1))
	return {
		"sa": sa_of(r[1]), "label": label, "burn_name": None, "book_number": book if "F2" in book else None,
		"category": text(r[2]).strip().lower(), "sex": None, "date_of_birth": str(dob) if dob else None,
		"dam_tag": re.match(r"\d*", label).group(0) or None, "dam_sa": sa_of(r[9]), "origin": "Born on Farm",
		"remarks": "Breeders: %s%s%s" % (text(r[2]).strip(), "; born %d (no day)" % year_only if year_only else "",
		                                "; weighed %s" % text(r[3]) if text(r[3]) not in ("", "N/A") else ""),
		"vaccinations": [],
	}


def calves_data(wb, young, by_sa, by_tag, notes):
	"""Calves data gives sex and a birth date for the 2026 calves; join it to the Breeders rows."""
	rows = rows_of(wb, "Calves data")
	seen, dupes, orphans, conflicts, added = set(), [], [], [], 0
	for r in rows[1:]:
		if num(r[0]) is None:
			continue
		sa = sa_of(r[1])
		dam_txt = text(r[3]).upper()
		label, dam_tag, dam_sa = None, None, None
		if re.match(r"^\d+[A-Z]$", dam_txt):           # the calf's own label, '2211B'
			label, dam_tag = dam_txt, re.match(r"\d+", dam_txt).group(0)
		elif num(r[3]) and num(r[3]) > 130000:
			dam_sa = sa_of(r[3])
		elif dam_txt:
			dam_tag = dam_txt
		found = candidates(text(r[5]))
		dob = found[0] if found else None             # typed as text, day-first: '1.7.2026' is 1 July
		sex = {"heifer": "Female", "bull": "Male"}.get(text(r[7]).lower())
		if sa and sa in seen:
			dupes.append("13%04d" % sa)
			continue
		if not (sa or dam_tag or dam_sa):
			orphans.append(text(r[0]))
			continue
		dam = by_sa.get(dam_sa) or by_tag.get(dam_tag)
		# Label and dam-and-birth-date before the tag: Calves data puts 131000 on 2215B (MOL F2-8) where
		# Breeders has SA 1000 on the bull 2215A, and the same for three more tags. A tag already on another
		# Breeders animal stays there; the calf it was also written against gets none.
		match = next((y for y in young if label and y["label"] == label), None) or \
			next((y for y in young if dam_tag and (y["dam_tag"], y["date_of_birth"]) == (dam_tag, str(dob))), None) or \
			next((y for y in young if sa and y["sa"] == sa), None)
		if sa:
			seen.add(sa)
		taken = sa and any(y["sa"] == sa and y is not match for y in young)
		if taken:
			conflicts.append("13%04d" % sa)
		if match:
			match.update(sex=sex or match["sex"], date_of_birth=str(dob) if dob else match["date_of_birth"])
			if not match["sa"] and not taken:
				match["sa"] = sa
			match["book_number"] = match["book_number"] or (text(r[2]) or None)
			continue
		if not label:
			used = {y["label"] for y in young}
			stem = dam_tag or (dam["old_tag"] if dam else None)
			label = next(stem + ch for ch in "ABCDEFGH" if stem + ch not in used) if stem else "13%04d" % sa
		young.append({
			"sa": None if taken else sa, "label": label, "burn_name": None, "book_number": text(r[2]) or None,
			"category": "calf",
			"sex": sex, "date_of_birth": str(dob) if dob else None, "dam_tag": dam_tag,
			"dam": dam["id"] if dam else None, "origin": "Born on Farm",
			"remarks": "Calves data" + ("" if dam else "; dam %s is not on Breeders" % (dam_tag or "13%04d" % dam_sa)),
			"vaccinations": [],
		})
		added += 1
	notes.append("Calves data: joined to the Breeders calf rows by label ('2211B'), then dam and birth date, then "
	             "SA tag; its typed day-first birth dates and its sex win. %d calves are only on Calves data "
	             "and are added. Its DAM column holds the calf's own label where it reads like '2211B'." % added)
	if dupes:
		notes.append("Calves data: tag %s appears twice (27 July and 30 August, both to dam 2722); the first is "
		             "kept, the second has no tag of its own and is skipped." % ", ".join(dupes))
	if orphans:
		notes.append("Calves data: row %s has no tag, no dam and no sex; skipped." % ", ".join(orphans))
	if conflicts:
		notes.append("Calves data: tags %s are also on other Breeders animals (Breeders has SA 1000 on the bull "
		             "2215A, Calves data puts 131000 on the calf 2215B). Breeders' tag is kept; the calf is joined by "
		             "its label or its dam and birth date and keeps no tag." % ", ".join(conflicts))


def _sex_from_dams(cows, young, notes):
	"""A weaner's sex is not on the sheet; its dam's 'calves produced' sometimes says it.

	When a dam's calves of known sex are taken out of her count and what is left is all one sex, her
	calves of unknown sex are that sex. Otherwise it stays unknown and is reported."""
	for c in cows:
		mine = [y for y in young if y["dam"] == c["id"] and y["category"] != "breeding bull"]
		left = list(c["calf_sexes"])
		for y in mine:
			if y["sex"] in left:
				left.remove(y["sex"])
		known = {s for s in left if s}
		unknown = [y for y in mine if not y["sex"]]
		if unknown and len(known) == 1 and None not in left and len(left) >= len(unknown):
			for y in unknown:
				y["sex"] = next(iter(known))
				y["remarks"] += "; sex from dam's calves produced"
	missing = [y["label"] for y in young if not y["sex"]]
	for y in young:
		if not y["sex"]:
			y["sex"] = "Female"
			y["remarks"] += "; SEX NOT IN THE TRACKER, recorded Female: check"
	if missing:
		notes.append("Breeders: the sex of %d young animals (%s) is on neither sheet nor deducible from the dam's "
		             "'calves produced'; Animal needs one, so they are recorded Female with 'SEX NOT IN THE "
		             "TRACKER' in the remarks for the farm to correct." % (len(missing), ", ".join(missing)))


# --- sales -------------------------------------------------------------------


def _rfid_from(tag):
	"""'140171', '40244', '30990' (the RFID's last digits, sometimes one short) -> the full RFID."""
	t = RFID_TYPOS.get(tag, tag)
	if re.match(r"^1[34]\d{4}$", t):
		return "%s%s" % (RFID_PREFIX, t)
	if re.match(r"^[34]\d{4}$", t):
		return "%s1%s" % (RFID_PREFIX, t)
	return None


def steers_sold(wb, ids, notes):
	"""Every priced sale on Steers sold 2026. Month rows ('1 June') head each month's sales."""
	rows = rows_of(wb, "Steers sold 2026")
	month, out, skipped, off_month = None, [], [], 0
	for r in rows[1:]:
		c0 = r[0]
		if isinstance(c0, datetime) and all(v is None for v in r[1:5]):
			month = next(((d.year, d.month) for d in candidates(c0) if d.day == 1), month)
			continue
		rate, total = num(r[3]), num(r[4])
		raw = text(c0)
		if raw.lower() == "total" or (not raw and total and not rate):
			continue
		if not raw or not rate or not total or r[2] is None:
			if total and rate:
				skipped.append("%s %s kg" % (raw or "(no tag)", text(r[1])))
			continue
		weight_txt = text(r[1])
		# From September every sale is by the kg of carcass (700 KES) and says so only some of the time;
		# live cattle sell at 320-325 a kg.
		carcass_basis = "carcass" in text(r[5]).lower() or "CW" in weight_txt.upper() or rate > CARCASS_RATE_FROM
		paren = re.search(r"\(\s*(\d+(?:\.\d+)?)\s*(?:kgs?)?\s*\)", raw, re.I)
		tag = re.sub(r"\(.*?\)", "", raw).strip().upper()
		if carcass_basis:
			nums_ = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", weight_txt)]
			if isinstance(r[1], (int, float)):
				live, carcass = (float(paren.group(1)) if paren else None), float(r[1])
			else:
				live, carcass = nums_[0], nums_[1] if len(nums_) > 1 else None
		else:
			live, carcass = num(r[1]), None
		if not tag or not live:
			skipped.append("%s %s kg" % (raw or "(no tag)", weight_txt))
			continue
		found = candidates(r[2])
		sold = next((d for d in found if month and (d.year, d.month) == month), None)
		if not sold:
			sold = found[0] if found else None
			off_month += 1
		rfid = _rfid_from(tag)
		price = round(total / live, 2) if carcass_basis else rate
		out.append({
			"id": _unique(ids, rfid or "SOLD-%s-%s" % (_id_part(tag), sold.strftime("%y%m%d"))),
			"sheet": "Steers sold 2026", "tag": tag, "rfid": rfid, "burn_name": tag, "sex": "Male",
			"herd": "Finishers", "date": str(sold), "exit_weight_kg": live, "price_per_kg": price,
			"sale_price": total, "carcass_kg": carcass, "carcass_rate": rate if carcass_basis else None,
			"weights": [], "remarks": "",
		})
	notes.append("Steers sold 2026: %d sales. Each date is read in the month its block heads ('1 June' and the "
	             "rows under it); %d rows fit no reading in their month and keep their first one. Tags reused "
	             "across months ('29' sold in June and again in August) are different animals: a sold animal "
	             "with no RFID is 'SOLD-<tag>-<yymmdd>'. Oct-Nov sales give RFID digits ('140171', '40244' for "
	             "140244, '401137' for 140137) and are the RFID animal itself." % (len(out), off_month))
	notes.append("Steers sold 2026: carcass sales (700 or 620 KES a kg of carcass; every rate over 450 is one, "
	             "marked 'carcass weight' or not) give the live weight in the tag cell. The disposal's exit "
	             "weight is the live weight and its price per kg the total over it, so its sale price is the "
	             "sheet's total; the carcass weight and rate are in the reason.")
	if skipped:
		notes.append("Steers sold 2026: %s cannot be tied to an animal (no tag or no date) and are not seeded."
		             % "; ".join(skipped))
	return out


def moyale_sold(wb, ids, notes):
	"""Starter 1 - Moyale: weighed Feb-May 2026 and marked Sold, with no sale date or price."""
	rows = rows_of(wb, "Moyale sold")
	dates = header_dates([(c, rows[2][c]) for c in range(1, 12)], lo=date(2026, 1, 1))
	out = []
	for r in rows[3:]:
		tag = text(r[0]).upper()
		if not tag or "sold" not in [text(v).lower() for v in r[:12]]:
			continue
		weights = row_weights(r, dates)
		if not weights:
			continue
		last = weights[-1]
		out.append({
			"id": _unique(ids, "SOLD-%s-%s" % (_id_part(tag), date.fromisoformat(last["date"]).strftime("%y%m%d"))),
			"sheet": "Moyale sold", "tag": tag, "rfid": None, "burn_name": tag, "sex": "Male",
			"herd": "Starters/Breeders", "date": last["date"], "exit_weight_kg": last["kg"], "price_per_kg": None,
			"sale_price": None, "weights": weights,
			"remarks": "Moyale sold: sold after its last weighing; the tracker gives no sale date or price",
		})
	notes.append("Moyale sold: %d starters weighed %s and marked Sold, with no sale date or price. Each is "
	             "disposed as Sold on its last weighing date at that weight, with no price (the seeder records it "
	             "without the price check a live sale needs); the reason says the date and price are unknown. "
	             "Repeated tags in the list ('37', '80', '21') are separate animals."
	             % (len(out), ", ".join(str(d) for d in sorted(dates.values()))))
	return out


def breeders_sold(wb, ids, notes, health):
	rows = rows_of(wb, "Breeders sold")
	on = [as_typed(r[4]) for r in rows[1:] if r[4] is not None]
	common = max(set(on), key=on.count)
	out = []
	for r in rows[1:]:
		tag = text(r[0]).upper()
		if not tag:
			continue
		category = text(r[1]).lower()
		d = as_typed(r[4]) if r[4] is not None else common
		herd = "Heifers" if category == "heifer" else ("In-calf" if text(r[3]).lower() == "pregnant" else "Lactating")
		sid = _unique(ids, "SOLD-%s-%s" % (_id_part(tag), d.strftime("%y%m%d")))
		weight = num(r[2])
		out.append({
			"id": sid, "sheet": "Breeders sold", "tag": tag, "rfid": None, "burn_name": tag, "sex": "Female",
			"herd": herd, "date": str(d), "exit_weight_kg": weight, "price_per_kg": None, "sale_price": None,
			"weights": [], "category": category,
			"remarks": "Breeders sold: %s%s; sold after %s, the tracker gives no sale date or price"
			           % (category, ", " + text(r[3]) if text(r[3]) else "", d),
		})
		if r[4] is not None and text(r[5]):
			health.append({"animal": sid, "date": str(d), "event_type": "Vaccination",
			               "remarks": "Vaccinated: %s" % text(r[5])})
	notes.append("Breeders sold: %d heifers and cows with no sale date, price or dated weight. Their last dated "
	             "fact is the CBPP vaccination (%s); each is disposed as Sold on that day, without a price, and "
	             "the reason says so. Their undated weights are the exit weight only." % (len(out), common))
	return out


# --- old weighing sheets -------------------------------------------------------


def old_new_stock(wb):
	"""Rows of the four bought lots, July 2026: purchase date, seller, cost, drugs on arrival, weighings."""
	rows = rows_of(wb, "Old New stock")
	out, i = [], 0
	while i < len(rows):
		r = rows[i]
		if text(r[0]) != "Date purchased":
			i += 1
			continue
		source = text(rows[i - 1][1])
		drugs = {c: text(r[c]) for c in (7, 8, 9) if text(r[c])}
		first = next((rr for rr in rows[i + 1:] if text(rr[1])), None)
		bought = candidates(text(first[0]))[0]
		cells = [(c, r[c] if r[c] is not None else rows[i - 1][c]) for c in (3, 4)]
		dates = header_dates(cells, lo=bought)
		i += 1
		while i < len(rows) and text(rows[i][1]) and text(rows[i][1]) != "Average weight":
			rr = rows[i]
			on = candidates(text(rr[0]))
			tag = text(rr[1])
			if on and (num(rr[3]) is not None or text(rr[3]).lower() == "dead"):
				new = num(rr[2])
				keys = tag_keys(tag, plain="MOL") + ([("RFID", "13%04d" % int(new))] if new else [])
				given = ["%s %s" % (name, text(rr[c])) for c, name in drugs.items()
				         if text(rr[c]) and not re.match(r"^0(\.0)?(cc)?$", text(rr[c]))]
				out.append({
					"sheet": "Old New stock", "tag": tag, "keys": keys, "weights": row_weights(rr, dates),
					"acquired": str(on[0]), "cost": num(rr[6]), "source": source, "arrival_drugs": given,
					"dead": any("dead" in text(v).lower() or "died" in text(v).lower() for v in rr[:12]),
					"health": [],
				})
			i += 1
	return out


def _health(row, start):
	"""Dated vaccinations and dewormings to the right of a weighing row.

	The cells run date, name[, next due][, ...]: a date followed by a name is an event; a date
	followed by another date is a 'next due' and is not. 'every Tuesday' dipping is a routine, not
	an event. The CBPP strain 'T1/44' was drag-filled down the sheet into T1/45, T1/46...; it is one
	vaccine.
	"""
	cells = row[start:start + 16]
	out = []
	for j in range(len(cells) - 1):
		d = as_typed(cells[j]) if (isinstance(cells[j], datetime) or (isinstance(cells[j], str) and
		                                                              candidates(_date_text(cells[j])))) else None
		name = cells[j + 1]
		if not d or not isinstance(name, str) or candidates(_date_text(name)) or not name.strip():
			continue
		name = re.sub(r"T1/\d+", "T1/44", name.strip())
		if "deworm" in name.lower():
			med = text(cells[j + 2]) if j + 2 < len(cells) and isinstance(cells[j + 2], str) else ""
			out.append({"date": str(d), "event_type": "Deworming", "remarks": "Dewormed" + (": " + med if med else "")})
		else:
			out.append({"date": str(d), "event_type": "Vaccination", "remarks": "Vaccinated: " + name})
	return out


def old_finishers(wb):
	rows = rows_of(wb, "Old finishers")
	dates = header_dates([(c, rows[1][c]) for c in range(1, 16)], lo=date(2025, 11, 1))
	out = []
	for r in rows[2:]:
		tag = text(r[0])
		if not tag or text(r[4]).lower().startswith("avg"):
			continue
		out.append({"sheet": "Old finishers", "tag": tag, "keys": tag_keys(tag), "weights": row_weights(r, dates),
		            "health": _health(r, 16)})
	return out


def old_growers(wb):
	rows = rows_of(wb, "Old growers ")
	out, dates = [], None
	for r in rows:
		tag = text(r[0])
		if tag == "Tag No":
			dates = header_dates([(c, r[c]) for c in range(1, 14)], lo=date(2026, 1, 1))
			continue
		if dates is None or not tag or tag.lower().startswith("growers") or tag == "F":
			continue
		out.append({"sheet": "Old growers", "tag": tag, "keys": tag_keys(tag), "weights": row_weights(r, dates),
		            "health": _health(r, 15)})
	return out


def finishers_sold(wb):
	"""Weighings of the finishers sold Mar-Sep. Only the first four columns line up with the header
	(18 Dec, 11 Jan, 3 Feb, 2 Mar): further right the rows interleave gains and their own later
	weighings, which no header dates. Its RFID rows at the bottom name the RFIDs sold in Oct-Nov."""
	rows = rows_of(wb, "Finishers sold ")
	dates = header_dates([(c, rows[0][c]) for c in range(1, 5)], lo=date(2025, 11, 1))
	out, rfid_names = [], {}
	for r in rows[1:]:
		cells = [text(v) for v in r[:2]]
		rfid = next((c for c in cells if c.startswith("982")), None)
		if rfid:
			other = cells[0] if cells[0] != rfid else ""
			rfid_names[rfid.replace(" ", "")[-6:]] = other
			continue
		tag = text(r[0])
		if not tag:
			continue
		out.append({"sheet": "Finishers sold", "tag": tag, "keys": tag_keys(tag), "weights": row_weights(r, dates),
		            "health": []})
	return out, rfid_names


def attach_history(old, rfid_animals, sales, notes):
	"""Give each old-sheet row to the animal it is: an RFID animal still on the farm, else a sold one.

	A row matches an RFID animal through its old tag (see tag_keys) and only if the RFID animal's first
	weighing can follow the row's last (plausible): tags are reused, and a 160 kg grower of February is
	not the 300 kg finisher that carries his old number in October. A row that is not on the farm matches
	a sale by the tag number, again only if the sale weight can follow its last weighing. A match must be
	the only one both ways, or the row is left out.
	"""
	index = {}
	for a in rfid_animals:
		for k in tag_keys(a["old_tag"]) + [("RFID", a["tag"][-6:])]:
			index.setdefault(k, []).append(a)
	history, to_rfid, to_sale = {}, {}, {}
	stats = {"rfid": 0, "sale": 0, "dead": 0, "none": 0}
	ambiguous = set()
	for n, row in enumerate(old):
		last = row["weights"][-1] if row["weights"] else None
		for k in reversed(row["keys"]):
			hits = index.get(k, [])
			if len(hits) == 1 and (not last or plausible(hits[0]["weights"][0], last)):
				to_rfid.setdefault(hits[0]["tag"], []).append(n)
				break
	claimed = {n for ns in to_rfid.values() for n in ns}
	by_value = {}
	for s in sales:
		for k in tag_keys(s["tag"]) + ([("RFID", s["rfid"][-6:])] if s["rfid"] else []):
			by_value.setdefault(k[1], []).append(s)
	sale_rows = {}
	for n, row in enumerate(old):
		if n in claimed or row.get("sale_id"):
			continue
		last = row["weights"][-1] if row["weights"] else None
		fits = {s["id"]: s for k in row["keys"] for s in by_value.get(k[1], [])
		        if s["sheet"] == "Steers sold 2026" and last and
		        plausible({"date": s["date"], "kg": s["exit_weight_kg"]}, last)}
		if len(fits) == 1:
			sale_rows.setdefault(next(iter(fits)), []).append(n)
	for sid, ns in sale_rows.items():
		per_sheet = {}
		for n in ns:
			per_sheet.setdefault(old[n]["sheet"], []).append(n)
		one_each = [sn[0] for sn in per_sheet.values() if len(sn) == 1]
		s = next(x for x in sales if x["id"] == sid)
		if consistent([w for n in one_each for w in old[n]["weights"] if w["date"] < s["date"]] +
		              [{"date": s["date"], "kg": s["exit_weight_kg"]}]):
			to_sale[sid] = one_each
		else:
			ambiguous.update(one_each)
	used = set()
	rfid_by_tag = {a["tag"]: a for a in rfid_animals}
	for tag, ns in to_rfid.items():
		if len(ns) > 1 and (len({old[n]["sheet"] for n in ns}) < len(ns) or not consistent(
				[w for n in ns for w in old[n]["weights"]] + rfid_by_tag[tag]["weights"][:1])):
			ambiguous.update(ns)
			continue
		h = history.setdefault(tag, {"weights": [], "health": [], "sheets": []})
		for n in ns:
			_merge_row(h, old[n])
			used.add(n)
			if old[n].get("sale_id"):
				h.setdefault("sale_ids", []).append(old[n]["sale_id"])
			else:
				stats["rfid"] += 1
	sale_by_id = {s["id"]: s for s in sales}
	for sid, ns in to_sale.items():
		s = sale_by_id[sid]
		for n in ns:
			row = old[n]
			row = dict(row, weights=[w for w in row["weights"] if w["date"] < s["date"]],
			           health=[e for e in row["health"] if e["date"] <= s["date"]])
			_merge_row(s, row)
			used.add(n)
			stats["sale"] += 1
	for n, row in enumerate(old):
		if n not in used and n not in ambiguous and not row.get("sale_id"):
			stats["dead" if row.get("dead") else "none"] += 1
	notes.append("Old New stock, Old finishers, Old growers, Finishers sold: %d rows are animals still on the "
	             "farm (matched to an RFID animal by old tag, e.g. '74/ R 769' to MOL769, and only where the RFID "
	             "animal's first weighing can follow the row's last) and give it its earlier weighings, arrival "
	             "and treatments; %d rows are animals sold on Steers sold 2026 and give the sold animal its "
	             "weighings; %d rows are dead on the sheet; %d rows match nothing on the farm or in a sale, or "
	             "match more than one, and are not seeded (no exit is recorded for them, so creating them would "
	             "put animals on the farm that are not there); %d rows matched one animal together with another row "
	             "whose weighings cannot be the same animal's, and were left out." % (stats["rfid"], stats["sale"], stats["dead"], stats["none"],
	                                    len([n for n in ambiguous if not old[n].get("sale_id")])))
	notes.append("Weighing columns are dated by their headers, each the earliest reading at least two weeks after "
	             "the one before; a number under 80 kg in a weighing column is a gain and is ignored.")
	return history


def _merge_row(target, row):
	have = {w["date"] for w in target["weights"]}
	for w in row["weights"]:
		if w["date"] not in have:
			target["weights"].append(w)
			have.add(w["date"])
	target["weights"].sort(key=lambda w: w["date"])
	target.setdefault("health", [])
	seen = {(e["date"], e["event_type"]) for e in target["health"]}
	for e in row["health"]:
		if (e["date"], e["event_type"]) not in seen:
			target["health"].append(e)
			seen.add((e["date"], e["event_type"]))
	if row.get("arrival_drugs") and row.get("acquired"):
		if (row["acquired"], "Treatment") not in seen:
			target["health"].append({"date": row["acquired"], "event_type": "Treatment",
			                         "remarks": "On arrival from %s: %s" % (row["source"], ", ".join(row["arrival_drugs"]))})
	for k in ("acquired", "cost", "source"):
		if row.get(k) and not target.get(k):
			target[k] = row[k]
	if "sheets" in target and row["sheet"] not in target["sheets"]:
		target["sheets"].append(row["sheet"])


# --- medicine ------------------------------------------------------------------


def medicine(wb, notes):
	"""The shoat side of Medicine Cost, kept as read; see the note for why it is not seeded."""
	rows = rows_of(wb, "Medicine Cost")
	shoats, steers = [], []
	for r in rows[3:]:
		if text(r[0]) == "Date":
			break
		if text(r[1]) or text(r[2]):
			found = candidates(r[0]) if r[0] is not None else []
			shoats.append({"date": str(found[0]) if found else None, "date_as_typed": text(r[0]),
			               "medicine": text(r[1]) or text(r[2]), "quantity_ml": num(r[2]),
			               "cost": num(r[4]), "remarks": text(r[5])})
		if text(r[11]):
			steers.append({"date": text(r[9]), "animal": text(r[10]), "medicine": text(r[11]), "ml": num(r[12]),
			               "remarks": text(r[15])})
	notes.append("Medicine Cost, shoat side: %d rows are kept in the JSON (medicine_shoats) and not seeded. "
	             "None names a shoat group ('all shoats', '82 weaners, 37 rams and 16 he goats'), most are "
	             "before the groups' opening count (7 June 2026), and the herd-level record (Herd Treatment) "
	             "always issues stock; splitting a dose across groups would be invented." % len(shoats))
	notes.append("Medicine Cost, steer side: the arrival drugs (oxytetracycline, dexamethasone, buparvaquone, "
	             "Ivanor) are the Old New stock columns and are seeded per animal from there, as Treatment events "
	             "with no drug lines, so nothing is issued and nothing waits to be. The bloat treatment of "
	             "'MOL 802' on 27 May 2026 (catasol, liquid paraffin, epsom salt) is seeded if MOL802 is an "
	             "animal; the 'FMD @50/head', 'PPR' and 'Deworming forty heifers' lines name no animals.")
	return shoats, steers


def history(wb, animal_rows, notes):
	"""Everything the history steps of the seeder read. See the notes."""
	health = []
	breeder_rows = breeders(wb, notes)
	for a in breeder_rows:
		for v in a.pop("vaccinations"):
			health.append({"animal": a["id"], "date": v["date"], "event_type": "Vaccination",
			               "remarks": "Vaccinated: " + re.sub(r"T1/\d+", "T1/44", v["name"])})
	ids = {a["id"] for a in breeder_rows} | {a["tag"] for a in animal_rows}
	sales = steers_sold(wb, ids, notes) + moyale_sold(wb, ids, notes) + breeders_sold(wb, ids, notes, health)
	fin_rows, rfid_names = finishers_sold(wb)
	for s in sales:
		if s["rfid"] and rfid_names.get(s["rfid"][-6:]):
			s["burn_name"] = rfid_names[s["rfid"][-6:]]
	on_farm = {a["tag"] for a in animal_rows}
	for s in sales:
		if s["rfid"] and s["rfid"] in on_farm:
			raise SystemExit("%s is sold on %s and also in an RFID tab" % (s["rfid"], s["date"]))
	old = old_new_stock(wb) + old_finishers(wb) + old_growers(wb) + fin_rows
	# A Moyale starter marked Sold that is in an RFID tab today was not sold: it is that RFID animal.
	moyale = [{"sheet": "Moyale sold", "tag": s["tag"], "keys": tag_keys(s["tag"]), "weights": s["weights"],
	           "health": [], "sale_id": s["id"]} for s in sales if s["sheet"] == "Moyale sold"]
	hist = attach_history(old + moyale, animal_rows, sales, notes)
	kept = {n for h in hist.values() for n in h.pop("sale_ids", [])}
	if kept:
		sales = [s for s in sales if s["id"] not in kept]
		notes.append("Moyale sold: %d starters marked Sold are in an RFID tab today (by old tag, with weights that "
		             "follow on); they are those RFID animals, not sales." % len(kept))
	shoat_meds, steer_meds = medicine(wb, notes)
	for m in steer_meds:
		if m["animal"]:
			keys = tag_keys(m["animal"])
			hit = [a["tag"] for a in animal_rows if set(tag_keys(a["old_tag"])) & set(keys)]
			if len(hit) == 1:
				on = candidates(m["date"])
				hist.setdefault(hit[0], {"weights": [], "health": [], "sheets": []})["health"].append({
					"date": str(on[0]), "event_type": "Treatment",
					"remarks": "%s %s ml: %s" % (m["medicine"], m["ml"], m["remarks"])})
	for s in sales:
		for e in s.pop("health", []):
			health.append(dict(e, animal=s["id"]))
	for tag, h in hist.items():
		for e in h.pop("health"):
			health.append(dict(e, animal=tag))
	health.sort(key=lambda e: (e["animal"], e["date"], e["event_type"]))
	notes.append("Health: %d events (Vaccination, Deworming, Treatment), each on one animal and backdated, with "
	             "no drug lines: a history record issues nothing and leaves nothing to reconcile. Fotivax on "
	             "'25/12/26' is Christmas 2025 (its next dose is due June 2026); CBPP is 6 September (old feedlot "
	             "sheets) and 6 October (Breeders), as Excel stored them, matching Medicine Cost's order. 'Every "
	             "Tuesday' Duodip dipping is a routine with no date and is not an event." % len(health))
	return breeder_rows, sales, hist, health, shoat_meds


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
	breeder_rows, sales, hist, health, shoat_meds = history(wb, animal_rows, notes)
	fuel_rows, diesel_rate = fuel(wb, notes)
	data = {
		"source": os.path.basename(path),
		"as_of": str(AS_OF),
		"feeds": feeds,
		"rations": rations,
		"shoat_concentrate": concentrate,
		"shoat_groups": shoat_groups,
		"tracker_latest": tracker,
		"herd_counts": herd_counts(tracker, rations, animal_rows + breeder_rows, notes),
		"animals": animal_rows,
		"breeders": breeder_rows,
		"sales": sales,
		"history": hist,
		"health": health,
		"medicine_shoats": shoat_meds,
		"labour": labour(wb, notes),
		"fuel": fuel_rows,
		"diesel_rate": diesel_rate,
		"notes": notes,
	}
	os.makedirs(os.path.dirname(OUT), exist_ok=True)
	with open(OUT, "w") as f:
		json.dump(data, f, indent=1, sort_keys=False)
		f.write("\n")
	print("wrote %s: %d feeds, %d rations, %d shoat groups, %d animals, %d breeders and calves, %d sales, "
	      "%d animals with history, %d health events, %d labour days, %d fuel rows"
	      % (os.path.relpath(OUT), len(feeds), len(rations), len(shoat_groups), len(animal_rows), len(breeder_rows),
	         len(sales), len(hist), len(health), len(data["labour"]), len(fuel_rows)))
	for n in notes:
		print(" - " + n)


if __name__ == "__main__":
	if len(sys.argv) != 2:
		raise SystemExit(__doc__)
	main(sys.argv[1])
