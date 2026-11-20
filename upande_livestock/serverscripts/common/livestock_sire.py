"""Livestock Sire helpers: splitting a code off a typed bull, matching, linking.

Pure functions first (tidy / split_code / name_key / label / propose), so the
matcher can be tested and run on a list of texts without a database; the
database parts (find, link_of, apply) are thin and total: a failed lookup gives
None, never an exception, because a sire lookup must not take down a service or
a birth.
"""

import re

import frappe

SEP = " · "

# A registration code at the end of the text: Dutch herdbook (NL734970583), two
# letters + 6 or more digits, or the Holstein form that begins with the studbook
# prefix (14HO14768, 097HO41741, 0200AY01123, 7HO132).
CODE_AT_END = re.compile(
	r"(?:^|[\s·,;:\-–(\[])"
	r"(NL\d{6,}|[A-Z]{2}\d{6,}|\d{1,4}[A-Z]{2}\d{2,})"
	r"[)\]]?\s*$",
	re.I,
)
TRAILING_JUNK = " \t·,;:-–"


def tidy(text):
	"""Single spaces, no edges."""
	return re.sub(r"\s+", " ", (text or "")).strip()


def split_code(text):
	"""("Dolmen NL734970583") -> ("Dolmen", "NL734970583"); no code -> (text, "")."""
	text = tidy(text)
	m = CODE_AT_END.search(text)
	if not m:
		return text, ""
	name = text[: m.start(1)].rstrip(TRAILING_JUNK + "([")
	return name or text[m.start(1):], m.group(1).upper()


def name_key(name):
	"""What two spellings of one bull share: case and spacing do not matter."""
	return tidy(name).upper()


def label(name, code=None):
	"""'Dolmen · NL734970583', or just the name when there is no code."""
	name, code = tidy(name), tidy(code)
	return f"{name}{SEP}{code}" if code else name


def propose(rows):
	"""Group typed sires into proposed Livestock Sire records.

	`rows` is [(text, source, count)], source a free tag ("event", "animal").
	A code makes a sire: the same code is one bull however it is spelt. A text
	with no code joins the coded bull of the same name when exactly one exists;
	otherwise it becomes a name-only bull (several codes under one name is
	ambiguous, so it is not guessed). Returns (sires, text_to_key) where each sire
	is {name, code, key, aliases, counts} and text_to_key maps the raw text to the
	sire's key (code, else name key).
	"""
	by_code, by_name, text_to_key = {}, {}, {}
	pending = []

	def sire_for(key, name, code):
		s = by_code.setdefault(key, {"name": name, "code": code, "key": key,
		                             "aliases": {}, "counts": {}, "_best": (-1, False)})
		return s

	for raw, source, count in rows:
		text = tidy(raw)
		if not text:
			continue
		name, code = split_code(text)
		if code:
			s = sire_for(code, name, code)
			_add(s, text, source, count, name)
			text_to_key[text] = text_to_key[raw] = code
		else:
			pending.append((raw, text, source, count, name))
	for s in by_code.values():
		by_name.setdefault(name_key(s["name"]), []).append(s)
	name_only = {}
	for raw, text, source, count, name in pending:
		k = name_key(name)
		coded = by_name.get(k) or []
		if len(coded) == 1:
			s = coded[0]
		else:
			s = name_only.setdefault(k, {"name": name, "code": "", "key": k,
			                             "aliases": {}, "counts": {}, "_best": (-1, False)})
		_add(s, text, source, count, name)
		text_to_key[text] = text_to_key[raw] = s["key"]
	sires = sorted(list(by_code.values()) + list(name_only.values()), key=lambda s: s["name"].upper())
	for s in sires:
		s.pop("_best", None)
		s["aliases"] = sorted(s["aliases"], key=str.lower)
	return sires, text_to_key


def _add(s, text, source, count, name):
	s["aliases"][text] = True
	s["counts"][source] = s["counts"].get(source, 0) + count
	# The display name: the most-used spelling, a mixed-case one on a tie.
	best = (count, name != name.upper())
	if best > s["_best"]:
		s["_best"] = best
		s["name"] = name


# ---- database side ----

def find(text):
	"""The Livestock Sire a typed bull or a label refers to, or None.

	Matches the label ('Dolmen · NL734970583'), the code inside any text, then a
	name that exactly one sire has. Never guesses between two.
	"""
	try:
		text = tidy(text)
		if not text:
			return None
		if frappe.db.exists("Livestock Sire", text):
			return text
		name, code = split_code(text)
		if code:
			hit = frappe.db.get_value("Livestock Sire", {"sire_code": code}, "name")
			if hit:
				return hit
		hits = frappe.get_all("Livestock Sire", filters={"sire_name": name}, pluck="name", limit=2)
		return hits[0] if len(hits) == 1 else None
	except Exception:
		return None


def for_item(item_code):
	"""The Livestock Sire whose straw this Item is, or None."""
	if not item_code:
		return None
	try:
		return frappe.db.get_value("Livestock Sire", {"semen_item": item_code}, "name") or None
	except Exception:
		return None


def label_of(sire):
	"""The shown text of a Livestock Sire name ('' when it cannot be read)."""
	if not sire:
		return ""
	try:
		row = frappe.db.get_value("Livestock Sire", sire, ["sire_name", "sire_code"], as_dict=True)
		return label(row.sire_name, row.sire_code) if row else ""
	except Exception:
		return ""


def match_all(dry_run=True):
	"""Create Livestock Sires from the distinct typed bulls and link the records.

	Reads Livestock Event.sire and Animal.sire_name; never rewrites the text.
	Reuses an existing Livestock Sire (same code, else same name) rather than
	making a second, so it is safe to run again. With dry_run it writes nothing and
	returns the proposal.
	"""
	rows = []
	for text, c in frappe.db.sql(
		"select sire, count(*) from `tabLivestock Event` where ifnull(sire,'')!='' "
		"and ifnull(sire_link,'')='' group by sire"
	):
		rows.append((text, "event", c))
	for text, c in frappe.db.sql(
		"select sire_name, count(*) from `tabAnimal` where ifnull(sire_name,'')!='' "
		"and ifnull(sire_link,'')='' group by sire_name"
	):
		rows.append((text, "animal", c))
	sires, text_to_key = propose(rows)

	items = _straw_items()
	out, key_to_name = [], {}
	for s in sires:
		existing = (frappe.db.get_value("Livestock Sire", {"sire_code": s["code"]}, "name")
		            if s["code"] else None) or find(s["name"])
		item = items.get(name_key(s["name"]))
		out.append({"name": s["name"], "code": s["code"], "label": label(s["name"], s["code"]),
		            "sire_type": "Semen", "semen_item": item, "aliases": s["aliases"],
		            "events": s["counts"].get("event", 0), "animals": s["counts"].get("animal", 0),
		            "exists": existing})
		if dry_run:
			key_to_name[s["key"]] = existing or (s["code"] or s["name"])
			continue
		if not existing:
			doc = frappe.get_doc({"doctype": "Livestock Sire", "sire_name": s["name"],
			                      "sire_code": s["code"] or None, "sire_type": "Semen",
			                      "semen_item": item, "active": 1}).insert(ignore_permissions=True)
			existing = doc.name
		key_to_name[s["key"]] = existing

	linked = {"events": 0, "animals": 0}
	for text, key in text_to_key.items():
		target = key_to_name[key]
		if dry_run:
			continue
		for doctype, field, tag in (("Livestock Event", "sire", "events"), ("Animal", "sire_name", "animals")):
			frappe.db.sql(
				f"update `tab{doctype}` set sire_link=%s where `{field}`=%s and ifnull(sire_link,'')=''",
				(target, text),
			)
			linked[tag] += frappe.db.sql("select row_count()")[0][0]
	return {
		"dry_run": 1 if dry_run else 0,
		"distinct_sires": len(out),
		"with_code": sum(1 for s in out if s["code"]),
		"without_code": sum(1 for s in out if not s["code"]),
		"to_create": sum(1 for s in out if not s["exists"]),
		"events_to_link": sum(s["events"] for s in out),
		"animals_to_link": sum(s["animals"] for s in out),
		"linked": None if dry_run else linked,
		"sires": out,
	}


def _straw_items():
	"""name key -> Item code for the semen items Service draws on (may be none)."""
	try:
		from upande_livestock.serverscripts.common import event_items

		groups = event_items.groups_for_event("Service")
		if not groups:
			return {}
		rows = frappe.get_all("Item", filters={"item_group": ["in", groups], "disabled": 0},
		                      fields=["name", "item_name"])
		return {name_key(r.item_name): r.name for r in rows}
	except Exception:
		return {}
