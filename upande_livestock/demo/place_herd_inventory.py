# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Put the animals where the 26 August 2026 inventory says they are.

The inventory is the farm's own count and is the truth about where an animal
stands today; the site's herds drifted from it. Matching is on name AND date of
birth, falling back to name alone — the site has no book number on any record,
which is the very thing this also fixes.

TWO NAMES FOR ONE HERD. The inventory writes "LACTATION GROUP 1" where the site
holds "Lactating group 1", and "12 MONTHS-SERVICE" where the site holds
"12 MONTHS-SERVICE (BULLYING HEIFERS)". Taken literally that reads as 186
animals changing herd; mapped, it is a handful of real moves. Every difference
that looks like a mass migration deserves that second look.

    bench --site <site> execute upande_livestock.demo.place_herd_inventory.run
    bench --site <site> execute upande_livestock.demo.place_herd_inventory.run --kwargs "{'apply': True}"
"""

import json
import re
from collections import Counter

import frappe

DATA = ("/tmp/claude-1001/-home-ubuntu-stive-code-frappe15-apps-upande-scp/"
        "b6c1bfb1-0cbb-4dc9-8993-2881a8b84c4a/scratchpad/herd_inventory.json")

# What the inventory calls a herd -> what this site calls it.
HERD = {
	"LACTATION GROUP 1": "Lactating group 1",
	"LACTATION GROUP 2": "LACTATION GROUP 2",
	"12 MONTHS-SERVICE": "12 MONTHS-SERVICE (BULLYING HEIFERS)",
	"4-12 MONTHS (WEANERS)": "4-12 MONTHS (WEANERS)",
	"INCALF HEIFERS": "INCALF HEIFERS",
	"STEAMERS": "STEAMERS",
	"0-2": "0-2",
	"2-4": "2-4",
}


def _norm(s):
	return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _clean_book(raw):
	"""Tidy a book number without inventing one.

	Two transcription habits run through the sheet: a letter O where a zero
	belongs (AO63/20 beside A028/19 — the same series typed two ways), and a
	backslash for the separator. Four entries are not book numbers at all and are
	left exactly as found rather than guessed at.
	"""
	b = (raw or "").strip().replace("\\", "/")
	m = re.match(r"^A[O0](\d{2})/(\d{2})$", b, re.I)
	if m:
		return "A0{}/{}".format(m.group(1), m.group(2))
	m = re.match(r"^A(\d{3})/(\d{2})$", b, re.I)
	if m:
		return "A{}/{}".format(m.group(1), m.group(2))
	return b


def run(apply=False):
	apply_ = bool(apply)
	rows = json.load(open(DATA))
	animals = frappe.get_all(
		"Animal", fields=["name", "burn_name", "current_herd", "date_of_birth", "book_number"],
		limit_page_length=0,
	)
	by_name = {}
	for a in animals:
		by_name.setdefault(_norm(a.burn_name), []).append(a)

	moved = booked = missing = unchanged = 0
	unmatched, real_moves, bad_book = [], [], []

	for r in rows:
		herd = HERD.get(r["group"])
		if not herd or not frappe.db.exists("Herds", herd):
			unmatched.append((r, "herd {!r} does not map".format(r["group"])))
			continue

		cands = by_name.get(_norm(r["name"]), [])
		dob = [a for a in cands if str(a.date_of_birth or "") == (r["birth_date"] or "")]
		pick = dob[0] if dob else (cands[0] if len(cands) == 1 else None)
		if not pick:
			missing += 1
			unmatched.append((r, "no animal named {!r}".format(r["name"])))
			continue

		book = _clean_book(r["book_number"])
		if not re.match(r"^A\d{3}/\d{2}$", book):
			bad_book.append((r["name"], r["book_number"]))

		if pick.current_herd != herd:
			real_moves.append((pick.name, pick.current_herd, herd))
			if apply_:
				frappe.db.set_value("Animal", pick.name, "current_herd", herd, update_modified=False)
			moved += 1
		else:
			unchanged += 1

		if book and pick.book_number != book:
			booked += 1
			if apply_:
				frappe.db.set_value("Animal", pick.name, "book_number", book, update_modified=False)

	if apply_:
		# EVERY herd, not only the ones the inventory names. BULLS appears in
		# neither the sheet nor the mapping, and refreshing only the mapped herds
		# left its count reading 10 where 8 animals were live.
		for herd in frappe.get_all("Herds", pluck="name"):
			n = frappe.db.count("Animal", {
				"current_herd": herd,
				"status": ["not in", ["Dead", "Deceased", "Sold", "Culled", "Disposed"]],
				"disabled": 0,
			})
			frappe.db.set_value("Herds", herd, "number_of_animals", n, update_modified=False)
		frappe.db.commit()

	print("MODE:", "APPLY" if apply_ else "dry run")
	print("\n{} inventory rows against {} animals".format(len(rows), len(animals)))
	print("  already in the right herd   : {}".format(unchanged))
	print("  moved to the inventory herd : {}".format(moved))
	print("  book numbers set            : {}".format(booked))
	print("  no matching animal          : {}".format(missing))

	if real_moves:
		print("\n  where they moved to:")
		for g, n in Counter(t for _a, _f, t in real_moves).most_common():
			print("     {:<44} {}".format(g[:44], n))
		print("\n  a few:")
		for a, f, t in real_moves[:6]:
			print("     {:<24} {:<30} -> {}".format(a[:24], (f or "(none)")[:30], t))

	clashes = {}
	for a in frappe.get_all("Animal", filters=[["book_number", "is", "set"]],
	                        fields=["name", "book_number"], limit_page_length=0):
		clashes.setdefault(a.book_number, []).append(a.name)
	shared = {b: names for b, names in clashes.items() if len(names) > 1}
	if shared:
		print("\n  book numbers on more than one animal — the register needs a look:")
		for b, names in list(shared.items())[:6]:
			print("     {:<12} {}".format(b, ", ".join(names)))
		print("     Not deduplicated here: deciding which animal keeps a number is")
		print("     the farm's call, not a script's.")

	if bad_book:
		print("\n  book numbers left exactly as found — these are not register numbers:")
		for nm, b in bad_book:
			print("     {:<20} {!r}".format(nm[:20], b))

	if unmatched:
		print("\n  {} row(s) with no animal on this site:".format(len(unmatched)))
		for r, why in unmatched[:10]:
			print("     {:<20} {:<10} {:<24} {}".format(
				r["name"][:20], r["book_number"][:10], r["group"][:24], why))
		if len(unmatched) > 10:
			print("     … and {} more".format(len(unmatched) - 10))
		print("\n     These are animals the farm has and the system does not — mostly 2026")
		print("     book numbers, so calves born since the last data load. They are NOT")
		print("     created here: an animal needs a birth, a dam and a sex, and inventing")
		print("     one from a name and a date would leave it parentless.")
	return {"moved": moved, "booked": booked, "missing": missing}
