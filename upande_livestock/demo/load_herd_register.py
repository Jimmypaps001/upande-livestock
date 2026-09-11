# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Load the farm's register, and make an animal's number its name.

Two workbooks in references/ are the farm's own count as at 9 September 2026:
301 females in HERD INVENTORY, 12 bulls in BULL CALVES. This reads them and
leaves the site holding the same animals, in the same herds, under the same
numbers the farm writes in its book.

WHY THIS IS NOT A PATCH. It renames animals. A patch runs on every site it ever
reaches, including the live one, at whatever moment somebody runs `bench
migrate`. This runs when a person decides it should, having read the dry run.

    bench --site <site> execute upande_livestock.demo.load_herd_register.run
    bench --site <site> execute upande_livestock.demo.load_herd_register.run --kwargs "{'apply': True}"

WHAT IT WILL NOT DO. It retires nobody. 57 animals are active here and absent
from the 9 September count, which means either they left the farm or the count
missed them — and a script cannot tell those apart. They are renamed like
everyone else and listed at the end for the farm to rule on.
"""

import datetime
import os
import re
from collections import Counter, defaultdict

import frappe
from frappe.model.rename_doc import rename_doc

from upande_livestock.serverscripts.common import animal_id
from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES

REFERENCES = frappe.get_app_path("upande_livestock", "..", "references")
HEIFER_BOOK = "HERD INVENTORY AS AT 9 SEP 2026.xls"
BULL_BOOK = "BULL CALVES AS AT 9 SEP 2026.xls"

# What the register calls a herd -> what this site calls it. Taken literally the
# difference reads as 186 animals changing herd; mapped, it is a handful of real
# moves. Every difference that looks like a mass migration deserves that second
# look.
HERD = {
	"LACTATION GROUP 1": "Lactating group 1",
	"LACTATION GROUP 2": "LACTATION GROUP 2",
	"LACTATION GROUP 3": "Lactation Group 3 TEST HERD",
	"12 MONTHS-SERVICE": "12 MONTHS-SERVICE (BULLYING HEIFERS)",
	"4-12 MONTHS (WEANERS)": "4-12 MONTHS (WEANERS)",
	"INCALF HEIFERS": "INCALF HEIFERS",
	"STEAMERS": "STEAMERS",
	"BULLS": "BULLS",
	"0-2": "0-2",
	"2-4": "2-4",
}

# Created if absent. The farm calls it a test herd; it carries no feed recipe, so
# the report says so rather than letting a feed run discover it.
NEW_HERDS = {"Lactation Group 3 TEST HERD": {"herd_name": "Lactation Group 3 TEST HERD"}}

EXCEL_EPOCH = datetime.datetime(1899, 12, 30)


def _norm(s):
	return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _excel_date(value):
	"""A workbook serial to a date, or None. Times of day are discarded."""
	try:
		return (EXCEL_EPOCH + datetime.timedelta(days=float(value))).date()
	except (TypeError, ValueError):
		return None


def _read_sheet(path):
	import xlrd

	book = xlrd.open_workbook(path)
	sheet = book.sheets()[0]
	return [[str(c.value).strip() for c in sheet.row(r)] for r in range(1, sheet.nrows)]


def read_register():
	"""Both workbooks as one list of rows, females then bulls.

	`register` is what the book says. `id` is that tidied, or "" when the entry
	is not a number at all — ELLA, and two that Excel read as times of day. The
	raw text is kept either way; the report names every one.
	"""
	rows = []

	for r in _read_sheet(os.path.join(REFERENCES, HEIFER_BOOK)):
		name = r[1] if len(r) > 1 else ""
		if not name:
			continue
		raw = r[5] if len(r) > 5 else ""
		tidied = animal_id.tidy(raw)
		got = animal_id.parse(tidied)
		rows.append({
			"name": name,
			"sex": "Female",
			"register": raw,
			"id": got["id"] if got and got["prefix"] == "A" else "",
			"dob": _excel_date(r[4] if len(r) > 4 else None),
			"group": r[6] if len(r) > 6 else "",
		})

	for r in _read_sheet(os.path.join(REFERENCES, BULL_BOOK)):
		raw = r[1] if len(r) > 1 else ""
		got = animal_id.parse(animal_id.tidy(raw))
		if not got or got["prefix"] != "B":
			continue
		rows.append({
			"name": raw,
			"sex": "Male",
			"register": raw,
			"id": got["id"],
			# The bull sheet carries an age in months, not a birth date.
			"dob": _months_back(r[3] if len(r) > 3 else None),
			"group": r[2] if len(r) > 2 else "BULLS",
		})

	return rows


def _months_back(months):
	try:
		days = int(round(float(months) * 30.44))
	except (TypeError, ValueError):
		return None
	return (datetime.date.today() - datetime.timedelta(days=days))


class Allocator:
	"""Hands out free numbers, remembering what it has already promised.

	It is seeded with every number the register claims BEFORE anything is
	allocated. Without that, an animal whose register entry is broken could be
	handed a number the sheet is about to use two hundred rows later.
	"""

	def __init__(self, claimed):
		self.used = defaultdict(set)
		for key, seqs in claimed.items():
			self.used[key] |= set(seqs)

	def seed_from_site(self, prefix, yy):
		key = (prefix, yy)
		self.used[key] |= animal_id.taken(prefix, yy)

	def hold(self, animal_number):
		got = animal_id.parse(animal_number)
		if got:
			self.used[(got["prefix"], got["yy"])].add(got["seq"])

	def is_free(self, animal_number):
		"""Free both here and on the site.

		The site alone is not enough: a number a register row two hundred lines
		further down is about to claim looks free right up until it is taken.
		"""
		got = animal_id.parse(animal_number or "")
		if not got:
			return False
		key = (got["prefix"], got["yy"])
		if key not in self.used:
			self.seed_from_site(got["prefix"], got["yy"])
		return got["seq"] not in self.used[key] and not frappe.db.exists("Animal", got["id"])

	def take(self, sex, birth_date):
		prefix = animal_id.prefix_for_sex(sex)
		yy = animal_id.year_of(birth_date)
		key = (prefix, yy)
		if key not in self.used:
			self.seed_from_site(prefix, yy)
		seq = animal_id.next_free(prefix, yy, used=self.used[key])
		self.used[key].add(seq)
		return animal_id.format_id(prefix, seq, yy)


def _ensure_herds(apply_, report):
	for herd, fields in NEW_HERDS.items():
		if frappe.db.exists("Herds", herd):
			continue
		report["herds_created"].append(herd)
		if apply_:
			doc = frappe.new_doc("Herds")
			doc.update(fields)
			doc.insert(ignore_permissions=True)


def register_number_of(a):
	"""The number a site animal already carries, from wherever it was written.

	The register field first, then the display name — ten animals here were never
	given a book number but have one typed into their name, because there was
	nowhere else to put it.
	"""
	book = animal_id.tidy(a.get("book_number") or "")
	if animal_id.parse(book):
		return book
	return animal_id.extract(a.get("burn_name") or "")


def _site_animals():
	return frappe.get_all(
		"Animal",
		fields=["name", "burn_name", "book_number", "sex", "current_herd",
		        "date_of_birth", "status", "disabled"],
		limit_page_length=0,
	)


def _rename(current, target, apply_, report):
	"""Move a record onto its number. Every Link to Animal follows."""
	if current == target:
		return current
	if frappe.db.exists("Animal", target):
		report["rename_blocked"].append((current, target, "already taken"))
		return current
	report["renamed"].append((current, target))
	if apply_:
		# The model-level function, not frappe.rename_doc: only this one accepts
		# ignore_permissions, and a register load runs as whoever ran the bench
		# command rather than as a user with write on Animal.
		rename_doc("Animal", current, target, merge=False, force=False,
		           ignore_permissions=True)
		frappe.db.set_value("Animal", target, "tag_number", target, update_modified=False)
	return target if apply_ else current


def run(apply=False, limit=None):
	apply_ = bool(apply)
	rows = read_register()
	if limit:
		rows = rows[: int(limit)]

	report = defaultdict(list)
	report["mode"] = "APPLY" if apply_ else "dry run"

	# 1. Reserve every number the register claims, before allocating anything.
	claimed = defaultdict(set)
	for r in rows:
		got = animal_id.parse(r["id"]) if r["id"] else None
		if got:
			claimed[(got["prefix"], got["yy"])].add(got["seq"])
	allocator = Allocator(claimed)

	# 2. The herds the register needs.
	_ensure_herds(apply_, report)

	# 3. Index the site.
	site = _site_animals()
	by_book, by_name, seen_pairs = {}, defaultdict(list), defaultdict(list)
	for a in site:
		number = register_number_of(a)
		if number:
			by_book.setdefault(number, a)
		by_book.setdefault(a.name, a)
		by_name[_norm(a.burn_name)].append(a)
		seen_pairs[(_norm(a.burn_name), str(a.date_of_birth or ""))].append(a.name)
	# Same name, same day of birth, two records. The register lists one of them.
	for (nm, dob), names in seen_pairs.items():
		if len(names) > 1 and nm and dob:
			report["duplicate_records"].append((names, nm, dob))
	matched_site = set()

	# 4. Walk the register.
	for r in rows:
		herd = HERD.get(r["group"])
		if herd and not frappe.db.exists("Herds", herd) and herd not in NEW_HERDS:
			report["unmapped_herd"].append((r["name"], r["group"]))
			herd = None

		pick = by_book.get(r["id"]) if r["id"] else None
		if pick is not None and pick.name in matched_site:
			# Two register rows carrying one number — A047/22 names both HUDSON and
			# KYULA. The first row keeps the animal; the second must not be allowed
			# to overwrite it with a different cow's name and herd.
			report["shared_register_number"].append((r["name"], r["id"], pick.name))
			pick = None
		if not pick:
			cands = [a for a in by_name.get(_norm(r["name"]), []) if a.name not in matched_site]
			exact = [a for a in cands if r["dob"] and str(a.date_of_birth or "") == str(r["dob"])]
			pick = exact[0] if exact else (cands[0] if len(cands) == 1 else None)

		target = r["id"]
		if not target:
			# The register's entry is not a number — ELLA, and two Excel read as
			# times of day. Allocate from the gaps in the animal's own birth year.
			dob = r["dob"] or (pick.date_of_birth if pick else None)
			target = allocator.take(r["sex"], dob)
			report["allocated"].append((r["name"], r["register"], target, "register entry is not a number"))
		else:
			allocator.hold(target)

		if pick is None:
			report["created"].append((r["name"], target, r["group"]))
			if apply_:
				_create(r, target, herd)
			continue

		matched_site.add(pick.name)
		if pick.name != target and frappe.db.exists("Animal", target) and by_book.get(target) is not pick:
			# Two register rows carry the same number — A047/22 and AO21/24 each
			# name two animals. The first keeps it; the second is allocated a free
			# one, and both are named in the report for the farm to settle.
			fresh = allocator.take(r["sex"], r["dob"] or pick.date_of_birth)
			report["duplicate_register"].append((r["name"], target, fresh))
			target = fresh

		_update(pick, r, herd, apply_, report)
		_rename(pick.name, target, apply_, report)

	# 5. Everyone the register did not name.
	for a in site:
		if a.name in matched_site or animal_id.parse(a.name):
			continue
		book = register_number_of(a)
		target = book if allocator.is_free(book) else None
		if target:
			allocator.hold(target)
		else:
			target = allocator.take(a.sex, a.date_of_birth)
			report["allocated"].append(
				(a.burn_name or a.name, a.book_number or "(none)", target, "no register entry"))
		if (a.status or "Active") not in RETIRED_STATUSES and not a.disabled:
			report["absent_from_register"].append((a.burn_name or a.name, target, a.current_herd))
		_rename(a.name, target, apply_, report)

	if apply_:
		_recount()
		frappe.db.commit()

	_print(report, rows, site)
	return {k: (len(v) if isinstance(v, list) else v) for k, v in report.items()}


def _create(r, target, herd):
	doc = frappe.new_doc("Animal")
	doc.tag_number = target
	doc.burn_name = r["name"]
	doc.sex = r["sex"]
	doc.status = "Active"
	doc.origin = "Born on Farm"
	doc.date_of_birth = r["dob"]
	doc.acquisition_date = r["dob"]
	doc.current_herd = herd
	doc.book_number = r["register"] or None
	doc.company = frappe.db.get_single_value("Livestock Settings", "custom_default_company")
	doc.repro_status = "Bull" if r["sex"] == "Male" else "Open"
	doc.insert(ignore_permissions=True)


def _update(pick, r, herd, apply_, report):
	changes = {}
	if herd and pick.current_herd != herd:
		report["moved"].append((pick.name, pick.current_herd, herd))
		changes["current_herd"] = herd
	if r["dob"] and str(pick.date_of_birth or "") != str(r["dob"]):
		changes["date_of_birth"] = r["dob"]
	if r["name"] and (pick.burn_name or "") != r["name"]:
		changes["burn_name"] = r["name"]
	if r["register"] and (pick.book_number or "") != r["register"]:
		changes["book_number"] = r["register"]
	if changes and apply_:
		frappe.db.set_value("Animal", pick.name, changes, update_modified=False)
	return changes


def _recount():
	"""EVERY herd, not only the ones the register names — BULLS appears in the
	mapping but a herd the register never mentions would keep a stale count."""
	for herd in frappe.get_all("Herds", pluck="name"):
		frappe.db.set_value("Herds", herd, "number_of_animals", frappe.db.count("Animal", {
			"current_herd": herd,
			"status": ["not in", list(RETIRED_STATUSES)],
			"disabled": 0,
		}), update_modified=False)


def _print(report, rows, site):
	def n(key):
		return len(report.get(key) or [])

	print("\nMODE:", report["mode"])
	print("{} register rows against {} animals on this site\n".format(len(rows), len(site)))
	print("  created from the register   : {}".format(n("created")))
	print("  moved to the register herd  : {}".format(n("moved")))
	print("  renamed to their number     : {}".format(n("renamed")))
	print("  numbers allocated           : {}".format(n("allocated")))
	print("  herds created               : {}".format(n("herds_created")))

	if report.get("herds_created"):
		print("\n  HERDS CREATED — no feed recipe exists for these yet, so a feed run")
		print("  against one will fail until a BOM is assigned:")
		for h in report["herds_created"]:
			print("     {}".format(h))

	if report.get("moved"):
		print("\n  where they moved to:")
		for herd, count in Counter(t for _a, _f, t in report["moved"]).most_common():
			print("     {:<44} {}".format(herd[:44], count))

	if report.get("allocated"):
		print("\n  {} NUMBERS THE REGISTER DID NOT GIVE — check these against the".format(
			n("allocated")))
		print("  paper book; each was free in the animal's own birth year:")
		for name, was, got, why in report["allocated"][:40]:
			print("     {:<22} {:<12} -> {:<10} {}".format(name[:22], str(was)[:12], got, why))
		if n("allocated") > 40:
			print("     … and {} more".format(n("allocated") - 40))

	if report.get("duplicate_register"):
		print("\n  ONE NUMBER, TWO ANIMALS — the register says both. The first keeps it:")
		for name, wanted, got in report["duplicate_register"]:
			print("     {:<22} wanted {:<10} given {}".format(name[:22], wanted, got))

	if report.get("shared_register_number"):
		print("\n  {} REGISTER ROWS SHARE A NUMBER WITH AN EARLIER ROW. The first".format(
			n("shared_register_number")))
		print("  row keeps the animal; the second is treated as its own animal and")
		print("  given a free number:")
		for name, number, held_by in report["shared_register_number"]:
			print("     {:<22} wanted {:<10} held by {}".format(name[:22], number, held_by[:28]))

	if report.get("duplicate_records"):
		print("\n  {} ANIMALS RECORDED TWICE — same name, same day of birth. The".format(
			n("duplicate_records")))
		print("  register lists one of each; the other is given a free number and")
		print("  kept, because deleting an animal with events behind it is the")
		print("  farm's call, not a script's:")
		for names, nm, dob in report["duplicate_records"][:20]:
			print("     {:<18} {:<12} {}".format(nm[:18], dob, ", ".join(names)[:60]))

	if report.get("rename_blocked"):
		print("\n  could not be renamed:")
		for cur, target, why in report["rename_blocked"][:20]:
			print("     {:<28} -> {:<10} {}".format(cur[:28], target, why))

	if report.get("absent_from_register"):
		print("\n  {} ACTIVE ANIMALS THE 9 SEPTEMBER COUNT DOES NOT LIST.".format(
			n("absent_from_register")))
		print("  Nothing has been retired — a script cannot tell an animal that left")
		print("  the farm from one the count missed. The farm decides:")
		for name, number, herd in report["absent_from_register"][:60]:
			print("     {:<22} {:<10} {}".format(name[:22], number, (herd or "(no herd)")[:36]))
		if n("absent_from_register") > 60:
			print("     … and {} more".format(n("absent_from_register") - 60))
