# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A year of Mutara's feeding, from its tracker, as Livestock Feed History.

    bench --site mutara.local execute upande_livestock.demo.seed_mutara_feed_history.execute

Any other site (live) needs force=True:

    bench --site <live> execute upande_livestock.demo.seed_mutara_feed_history.execute --kwargs "{'force': True}"

RECORDS ONLY, everywhere. The farm fed from November 2025 without this app and
never received that feed into the system, so this writes no Stock Entry, no
Work Order and nothing to the ledger — on a .local site as much as on live.
The history is there so cost per animal and the Rations page can show those
days (`costing._maths.merge_feed` uses a history day only where the stock
ledger has no feed issue for that herd and day).

Reads demo/data/mutara_feed_history.json (scripts/extract_mutara_feed_history.py;
its `notes` list every judgement made on the sheet). Run after
demo/seed_mutara_tracker, which makes the herds and feed Items these link to; a
record whose herd or item is missing is skipped and counted, not invented.

Idempotent: a herd-day already on the site is left alone when it matches the
JSON and brought into line when it does not, so a second run changes nothing.
"""

import json
import os

import frappe
from frappe.utils import flt, getdate

DOCTYPE = "Livestock Feed History"
DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mutara_feed_history.json")
COMMIT_EVERY = 200


def load(path=DATA_PATH):
	with open(path) as f:
		return json.load(f)


def _lines(rec):
	return [{"item": line["item"], "qty_kg": flt(line["qty_kg"]), "rate": flt(line["rate"])} for line in rec["lines"]]


def _same(doc, rec, source):
	"""Does the saved record already say what the JSON says? Compared on what the sheet gave, not on derived totals."""
	have = sorted((r.item, round(flt(r.qty_kg), 3), round(flt(r.rate), 2)) for r in doc.items)
	want = sorted((x["item"], round(x["qty_kg"], 3), round(x["rate"], 2)) for x in _lines(rec))
	return (have == want and int(doc.head_count or 0) == int(rec["head_count"])
	        and round(flt(doc.total_cost), 2) == round(flt(rec["total_cost"]), 2) and (doc.source or "") == source)


def _write(doc, rec, source):
	doc.update({"date": getdate(rec["date"]), "herd": rec["herd"], "head_count": int(rec["head_count"]),
	            "total_cost": flt(rec["total_cost"]), "source": source})
	doc.set("items", [])
	for line in _lines(rec):
		doc.append("items", line)
	doc.save(ignore_permissions=True)


def seed(data):
	"""Write each record that is missing or out of step; return the counts."""
	source = data.get("source_label") or "Tracker"
	herds = set(frappe.get_all("Herds", pluck="name", limit=0))
	items = set(frappe.get_all("Item", filters={"name": ["in", sorted(
		{line["item"] for rec in data["records"] for line in rec["lines"]})]}, pluck="name", limit=0))
	have = {(str(r.date), r.herd): r.name for r in frappe.get_all(DOCTYPE, fields=["name", "date", "herd"], limit=0)}
	counts = {"created": 0, "updated": 0, "unchanged": 0, "no_herd": 0, "no_item": 0}
	missing = {"herds": set(), "items": set()}
	for n, rec in enumerate(data["records"], start=1):
		if rec["herd"] not in herds:
			counts["no_herd"] += 1
			missing["herds"].add(rec["herd"])
			continue
		absent = [line["item"] for line in rec["lines"] if line["item"] not in items]
		if absent:
			counts["no_item"] += 1
			missing["items"].update(absent)
			continue
		name = have.get((rec["date"], rec["herd"]))
		if name:
			doc = frappe.get_doc(DOCTYPE, name)
			if _same(doc, rec, source):
				counts["unchanged"] += 1
				continue
			_write(doc, rec, source)
			counts["updated"] += 1
		else:
			_write(frappe.new_doc(DOCTYPE), rec, source)
			counts["created"] += 1
		if n % COMMIT_EVERY == 0:
			frappe.db.commit()
	frappe.db.commit()
	return counts, missing


def execute(force=False):
	"""Load the tracker's feed history. Records only; see the module docstring."""
	site = frappe.local.site
	if not force and not site.endswith(".local"):
		frappe.throw("{} is not a .local site. Pass force=True only with approval.".format(site))
	if not frappe.db.table_exists(DOCTYPE):
		frappe.throw("{} is not installed on {}: migrate first.".format(DOCTYPE, site))
	data = load()
	print("feed history from {} ({} records, as of {}); no stock is posted".format(
		data["source"], len(data["records"]), data["as_of"]))
	counts, missing = seed(data)
	print("done: {}".format(counts))
	if missing["herds"]:
		print("  herds not on the site (run seed_mutara_tracker first): " + ", ".join(sorted(missing["herds"])))
	if missing["items"]:
		print("  items not on the site: " + ", ".join(sorted(missing["items"])))
	return counts
