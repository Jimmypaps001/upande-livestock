"""Park the animals the 9 September count does not list in a herd of their own.

The farm's count is the farm's truth about what is standing in the yard. An
animal the count does not mention is not there, and while it sits in a
production herd the feed run manufactures a ration for it every morning.

Only the ones still Active move. The 35 already marked Sold, Culled or Dead are
excluded from every head count by their status already, and the app keeps
`current_herd` on a disposed animal ON PURPOSE so its history stays readable —
moving those would destroy that and change no number.

The move is a Movement event, not a field write: it is a real change of place
and it belongs in the animal's history like any other.

    bench --site <site> execute upande_livestock.demo.park_unlisted.run
    bench --site <site> execute upande_livestock.demo.park_unlisted.run --kwargs "{'apply': True}"
"""
import json
import os
import re
from collections import Counter

import frappe

REFS = frappe.get_app_path("upande_livestock", "..", "references")
HERD = "Culled"
RETIRED = ("Dead", "Deceased", "Sold", "Culled", "Disposed", "Transferred Out")


def _n(s):
	return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def register_names():
	import xlrd

	names = Counter()
	sh = xlrd.open_workbook(os.path.join(REFS, "HERD INVENTORY AS AT 9 SEP 2026.xls")).sheets()[0]
	for r in range(1, sh.nrows):
		v = [str(c.value).strip() for c in sh.row(r)]
		if len(v) > 1 and v[1]:
			names[_n(v[1])] += 1
	sh = xlrd.open_workbook(os.path.join(REFS, "BULL CALVES AS AT 9 SEP 2026.xls")).sheets()[0]
	for r in range(1, sh.nrows):
		v = [str(c.value).strip() for c in sh.row(r)]
		if len(v) > 1 and re.match(r"^B[O0-9]{3}[/\\]\d{2}$", (v[1] or "").upper()):
			names[_n(v[1])] += 1
	return names


def to_park():
	"""Active animals whose name the count does not carry at all.

	A name the count carries fewer times than this site does is left alone: the
	surplus is real, but which copy is the surplus is not a script's call.
	"""
	reg = register_names()
	rows = frappe.get_all(
		"Animal",
		fields=["name", "burn_name", "current_herd", "status", "disabled"],
		limit_page_length=0,
	)
	out, ambiguous = [], []
	here = Counter(_n(a.burn_name) for a in rows)
	for a in rows:
		k = _n(a.burn_name)
		if (a.status or "Active") in RETIRED or a.disabled:
			continue
		if reg.get(k, 0) == 0:
			out.append(a)
		elif here[k] > reg[k]:
			ambiguous.append(a)
	return out, ambiguous


def run(apply=False, dump=None):
	apply_ = bool(apply)
	parked, ambiguous = to_park()

	print("\nMODE: {}".format("APPLY" if apply_ else "dry run"))
	print("\n  to park in {!r} : {}".format(HERD, len(parked)))
	print("  left alone (name shared with the count): {}".format(len(ambiguous)))
	for herd, n in Counter(a.current_herd for a in parked).most_common():
		print("     {:<44} {}".format((herd or "(no herd)")[:44], n))
	for a in ambiguous:
		print("     ambiguous: {:<20} {:<12} {}".format(
			(a.burn_name or "")[:20], a.name, a.current_herd))

	if dump:
		json.dump(sorted(a.burn_name for a in parked), open(dump, "w"))
		print("\n  names -> {}".format(dump))

	if not apply_:
		print("\n  nothing written. Re-run with apply=True.")
		return {"parked": 0, "would_park": len(parked)}

	if not frappe.db.exists("Herds", HERD):
		doc = frappe.new_doc("Herds")
		doc.herd_name = HERD
		doc.insert(ignore_permissions=True)
		print("\n  created herd {!r}".format(HERD))

	operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	done = 0
	for a in parked:
		if a.current_herd == HERD:
			continue
		move = frappe.new_doc("Livestock Event")
		move.event_type = "Movement"
		move.animal = a.name
		move.event_date = frappe.utils.today()
		move.new_herd = HERD
		move.current_herd = a.current_herd or ""
		move.operator = operator
		move.remarks = "Not listed in the 9 September 2026 herd inventory"
		move.insert(ignore_permissions=True)
		move.submit()
		done += 1
	frappe.db.commit()
	print("\n  parked {}".format(done))
	print("  {} now holds {}".format(HERD, frappe.db.get_value("Herds", HERD, "number_of_animals")))
	return {"parked": done}
