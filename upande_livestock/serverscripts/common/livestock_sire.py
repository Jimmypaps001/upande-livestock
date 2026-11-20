"""Livestock Sire helpers: splitting a code off a typed bull, matching, linking.

Pure functions first (tidy / split_code / code_key / base_key / propose), so the
matcher can be tested and run on a list of texts without a database; the
database parts (find, link_of, match_all) are thin and total: a failed lookup
gives None, never an exception, because a sire lookup must not take down a
service or a birth.

One bull, one unique code. The code is read off the typed text ("ARCANA
14HO14768"), off the semen straw Item's name ("Baymax Semen 14HO14919"), and the
two are reconciled to one sire. Spelling variants of a name (PRINCIPAL / PRINCIPAL
PP, RICOCHET / RICCOCHET) are the same bull.
"""

import re

import frappe

SEP = " · "

# A registration code: Dutch herdbook (NL734970583), two letters + 6 or more
# digits, the Holstein form that begins with the studbook prefix (14HO14768,
# 097HO41741, 0200AY01123, 7HO132), or the same with a zero typed for the O
# (250H0015388).
CODE_RE = r"(NL\d{6,}|[A-Z]{2}\d{6,}|\d{1,4}[A-Z]{2}\d{2,}|\d{1,4}H0\d{5,})"
CODE_AT_END = re.compile(r"(?:^|[\s·,;:\-–(\[])" + CODE_RE + r"[)\]]?\s*$", re.I)
CODE_ANYWHERE = re.compile(r"(?:^|[\s·,;:\-–(\[])" + CODE_RE + r"(?=$|[\s·,;:\-–)\]])", re.I)
TRAILING_JUNK = " \t·,;:-–"

# Words a straw Item's name wraps around the bull's name, and the endings a
# spelling variant adds (polled, red factor, embryo, sexed).
ITEM_NOISE = {"SEMEN", "SEXED", "DELTA", "SIR", "YX", "SIRYX", "HOOGSTRATEN", "KOEPON", "STRAW", "STRAWS"}
NAME_SUFFIX = {"F", "RF", "PP", "P", "ET", "SEXED", "RED"}
# Items that are not a bull's straw.
NOT_A_BULL = {"", "DEFROSTER", "TEST SIRE", "STRAW TEST SIRE"}
MAX_EDIT = 2
MIN_FUZZY_LEN = 5


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
	return name or text[m.start(1):], canon_code(m.group(1))


def canon_code(code):
	"""Upper case, and the zero typed for the O in a Holstein code put right."""
	code = tidy(code).upper()
	m = re.match(r"^(\d{1,4})H0(\d{5,})$", code)
	if m:
		return m.group(1) + "HO" + m.group(2).lstrip("0")
	return code


def code_key(code):
	"""What two spellings of one code share (07923 and 7923 are the same number)."""
	code = canon_code(code)
	m = re.match(r"^(\d{1,4})HO(\d+)$", code)
	return m.group(1) + "HO" + m.group(2).lstrip("0") if m else code


def code_tail(code):
	"""The serial number of a Holstein code, whatever the studbook prefix: 7HO15142 and
	507HO15142 both end 15142."""
	m = re.match(r"^\d{1,4}HO(\d+)$", canon_code(code))
	return m.group(1).lstrip("0") if m else ""


def name_key(name):
	"""What two spellings of one bull share: case and spacing do not matter."""
	return tidy(name).upper()


def base_key(name):
	"""The bull's name stripped of Item wording and variant endings, no spaces:
	'Semen Delta Stormer-F' -> STORMER, 'PRINCIPAL PP' -> PRINCIPAL, 'FAST LANE' -> FASTLANE."""
	words = [w for w in re.split(r"[^A-Z0-9]+", name_key(name)) if w]
	words = [w for w in words if w not in ITEM_NOISE]
	while len(words) > 1 and words[-1] in NAME_SUFFIX:
		words.pop()
	return "".join(words)


def edit_distance(a, b):
	prev = list(range(len(b) + 1))
	for i, ca in enumerate(a, 1):
		cur = [i]
		for j, cb in enumerate(b, 1):
			cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
		prev = cur
	return prev[-1]


def label(name, code=None):
	"""'Dolmen · NL734970583', or just the name when there is no code."""
	name, code = tidy(name), tidy(code)
	return f"{name}{SEP}{code}" if code else name


def item_bull(item_name):
	"""A straw Item's name -> (bull name, code); ('', '') when it is no bull's straw.

	'Baymax Semen 14HO14919' -> ('Baymax', '14HO14919'); 'Semen Delta Stormer-F'
	-> ('Stormer F', ''): the name keeps its ending, base_key strips it to compare.
	"""
	text = tidy(item_name)
	code = ""
	m = CODE_ANYWHERE.search(text)
	if m:
		code = canon_code(m.group(1))
		text = tidy(text[: m.start(1)] + " " + text[m.end(1):])
	words = [w for w in re.split(r"[\s\-–]+", text) if w and w.upper() not in ITEM_NOISE]
	name = " ".join(words)
	key = base_key(name)
	if key in NOT_A_BULL or not re.search(r"semen|sexed", item_name, re.I):
		return "", ""
	return name, code


def _group(name, code):
	return {"names": {}, "coded_names": {}, "codes": {}, "code": code, "name": name, "aliases": {}, "counts": {},
	        "items": [], "notes": [], "typed": 0}


def propose(rows, items=None):
	"""Group typed sires and straw Items into proposed Livestock Sire records.

	`rows` is [(text, source, count)], source a free tag ("service", "calving",
	"animal"); `items` is [(item_code, item_name)]. A code makes a sire: the same
	code is one bull however it is spelt, on a calf or on a straw's Item name. A
	text or Item with no code joins the coded bull of the same name (spelling
	variants such as PRINCIPAL / PRINCIPAL PP share a base name) when exactly one
	exists; otherwise it becomes a name-only bull (several codes under one name is
	ambiguous, so it is not guessed). Bulls whose names are one or two letters apart
	(RICOCHET / RICCOCHET) are merged when their codes do not disagree.

	Returns (sires, text_to_key). Each sire is {name, code, key, aliases, counts,
	items, notes}; text_to_key maps a raw typed text to the sire's key (code, else
	name key). `notes` say what was merged by spelling or left apart.
	"""
	groups = {}  # code key -> group
	pending = []  # name-only entries: (name, text, source, count, item_code or None, raw)
	text_to_gkey = {}
	order = []

	def new(name, code, key):
		g = _group(name, code)
		g["id"] = len(order)
		order.append(g)
		groups[key] = g
		return g

	def add_text(g, text, source, count, name, code_of_text=False):
		g["aliases"][text] = True
		g["counts"][source] = g["counts"].get(source, 0) + count
		g["names"][name] = g["names"].get(name, 0) + count
		g["typed"] += count
		if code_of_text:
			g["coded_names"][name] = g["coded_names"].get(name, 0) + count

	typed_entries = []
	for raw, source, count in rows:
		text = tidy(raw)
		if not text:
			continue
		name, code = split_code(text)
		typed_entries.append((raw, text, source, count, name, code))
	item_entries = []
	for item_code, item_name in items or []:
		name, code = item_bull(item_name)
		if name:
			item_entries.append((item_code, item_name, name, code))

	raw_to_group = {}
	for raw, text, source, count, name, code in typed_entries:
		if code:
			g = groups.get(code_key(code)) or new(name, code, code_key(code))
			add_text(g, text, source, count, name, True)
			raw_to_group[raw] = g
	for item_code, item_name, name, code in item_entries:
		if code:
			g = groups.get(code_key(code)) or new(name, code, code_key(code))
			g["items"].append((item_code, item_name))
			g["names"].setdefault(name, 0)

	def coded_for(base):
		return [g for g in order if g["code"] and any(base_key(n) == base for n in g["names"])]

	# A straw Item whose code differs from the calves' only by studbook prefix.
	for g in list(order):
		if g["code"] and not g["typed"] and g["items"]:
			tail = code_tail(g["code"])
			peers = [h for h in order if h is not g and h["typed"] and code_tail(h["code"]) == tail
			         and tail and any(base_key(n) in base_key(" ".join(x for x in g["names"]))
			                          or base_key(" ".join(g["names"])).startswith(base_key(n))
			                          for n in h["names"])]
			if len(peers) == 1:
				_merge(peers[0], g, f"straw code {g['code']} differs from {peers[0]['code']} only by studbook prefix")
				order.remove(g)
				groups = {k: v for k, v in groups.items() if v is not g}

	by_name_only = {}
	for raw, text, source, count, name, code in typed_entries:
		if code:
			continue
		base = base_key(name)
		coded = coded_for(base)
		if len(coded) == 1:
			g = coded[0]
		else:
			g = by_name_only.get(base) or by_name_only.setdefault(base, new(name, "", "name:" + base))
			if len(coded) > 1:
				g["ambiguous"] = True
				g["notes"].append("name matches %d coded bulls (%s): not guessed" % (
					len(coded), ", ".join(c["code"] for c in coded)))
		add_text(g, text, source, count, name)
		raw_to_group[raw] = g
	for item_code, item_name, name, code in item_entries:
		if code:
			continue
		base = base_key(name)
		coded = coded_for(base)
		if len(coded) == 1:
			g = coded[0]
		else:
			g = by_name_only.get(base) or by_name_only.setdefault(base, new(name, "", "name:" + base))
			if len(coded) > 1:
				g["ambiguous"] = True
				g["notes"].append("straw name matches %d coded bulls: not guessed" % len(coded))
		g["items"].append((item_code, item_name))

	# Spelling variants: one or two letters apart, codes that do not disagree.
	changed = True
	while changed:
		changed = False
		for a in list(order):
			for b in list(order):
				if a is b or a not in order or b not in order or a["id"] > b["id"]:
					continue
				if a["code"] and b["code"] and code_key(a["code"]) != code_key(b["code"]):
					continue
				if a.get("ambiguous") or b.get("ambiguous"):
					continue
				if _near(a, b):
					keep, drop = (a, b) if (a["code"] or not b["code"]) else (b, a)
					_merge(keep, drop, "merged by spelling: %s ~ %s" % (
						" / ".join(sorted(drop["names"], key=str.lower)), " / ".join(sorted(keep["names"], key=str.lower))))
					order.remove(drop)
					for r, g in raw_to_group.items():
						if g is drop:
							raw_to_group[r] = keep
					changed = True
					break
			if changed:
				break

	# Different codes under near names are not merged; say so.
	for i, a in enumerate(order):
		for b in order[i + 1:]:
			if a["code"] and b["code"] and code_key(a["code"]) != code_key(b["code"]) and _near(a, b, 1):
				for g, o in ((a, b), (b, a)):
					g["notes"].append("name close to %s (%s) but the code differs: kept apart" % (o["name"], o["code"]))

	sires = []
	for g in order:
		g["name"], g["code"] = _display(g)
		g["key"] = g["code"] or name_key(g["name"])
		g["aliases"] = sorted(g["aliases"], key=str.lower)
		g["items"] = sorted(set(g["items"]))
		g["variants"] = sorted({n for n in g["names"] if name_key(n) != name_key(g["name"])}, key=str.lower)
		sires.append({k: g[k] for k in ("name", "code", "key", "aliases", "counts", "items", "notes", "variants")})
	text_to_key = {}
	for raw, g in raw_to_group.items():
		text_to_key[raw] = text_to_key[tidy(raw)] = g["key"]
	sires.sort(key=lambda s: s["name"].upper())
	return sires, text_to_key


def _near(a, b, max_edit=MAX_EDIT):
	ka = {base_key(n) for n in a["names"]}
	kb = {base_key(n) for n in b["names"]}
	for x in ka:
		for y in kb:
			if x == y:
				return True
			if min(len(x), len(y)) >= MIN_FUZZY_LEN and edit_distance(x, y) <= max_edit:
				return True
	return False


def _merge(keep, drop, note):
	for k, v in drop["names"].items():
		keep["names"][k] = keep["names"].get(k, 0) + v
	for k, v in drop["coded_names"].items():
		keep["coded_names"][k] = keep["coded_names"].get(k, 0) + v
	for k, v in drop["counts"].items():
		keep["counts"][k] = keep["counts"].get(k, 0) + v
	keep["aliases"].update(drop["aliases"])
	keep["items"].extend(drop["items"])
	keep["notes"].extend(drop["notes"])
	keep["typed"] += drop["typed"]
	if not keep["code"] and drop["code"]:
		keep["code"] = drop["code"]
	elif keep["code"] and drop["code"] and keep["code"] != drop["code"]:
		keep["codes"][drop["code"]] = True
	keep["notes"].append(note)


def _display(g):
	"""The shown name: the most-used spelling among typed texts of a coded bull (its
	herdbook name as the calves carry it), a mixed-case one on a tie, else the
	Item's wording."""
	def rank(item):
		n, c = item
		return (c, n != n.upper())
	pool = g["coded_names"] or g["names"]
	name = max(pool.items(), key=rank)[0] if pool else g["name"]
	return name, g["code"]


# ---- database side ----

def find(text):
	"""The Livestock Sire a typed bull or a label refers to, or None.

	Matches the label ('Dolmen · NL734970583'), the code inside any text, then a
	name that exactly one sire has (spelling variants such as 'Principal PP' count
	as the name). Never guesses between two.
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
		if len(hits) == 1:
			return hits[0]
		base = base_key(name)
		if base and not code:
			rows = frappe.get_all("Livestock Sire", fields=["name", "sire_name"], limit=2000)
			hits = [r.name for r in rows if base_key(r.sire_name) == base]
			if len(hits) == 1:
				return hits[0]
		return None
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


def primary_item(items):
	"""Of a bull's straw Items, the one to link: not sexed, not a suffix variant, else the first."""
	if not items:
		return None
	ranked = sorted(items, key=lambda i: (bool(re.search(r"sexed", i[1], re.I)), len(i[1]), i[0]))
	return ranked[0][0]


def suggest_item(name, code, items):
	"""Of straw Items [(item_code, item_name)], the one that is this bull's, or None.

	Same reading as the matcher: the code (whatever the studbook prefix says of its
	number), else the base name, a coded straw not standing against a coded bull
	of another code. Of several, primary_item's pick."""
	name, code = tidy(name), canon_code(code or "")
	hits = []
	for item_code, item_name in items or []:
		bull, icode = item_bull(item_name)
		if not bull:
			continue
		if code and icode:
			ok = code_key(code) == code_key(icode) or (
				code_tail(code) and code_tail(code) == code_tail(icode) and base_key(bull) == base_key(name))
		else:
			ok = bool(base_key(name)) and base_key(bull) == base_key(name)
		if ok:
			hits.append((item_code, item_name))
	return primary_item(hits)


def straw_group():
	"""The item group the farm keeps its straws in (Livestock Settings)."""
	try:
		return frappe.db.get_single_value("Livestock Settings", "sire_item_group") or "Dairy Others"
	except Exception:
		return "Dairy Others"


def straw_candidates(q=None, limit=500):
	"""[{value, item_name, uom, group}] of Items that can be a sire's straw: in the
	straw group, or named semen. `q` narrows by any word of the code or name."""
	group = straw_group()
	conds = ["i.disabled=0", "(i.item_group=%(group)s or i.item_name like '%%semen%%' or i.item_name like '%%sexed%%')"]
	args = {"group": group, "limit": int(limit)}
	for n, w in enumerate((q or "").split()):
		conds.append(f"(i.item_name like %(w{n})s or i.name like %(w{n})s)")
		args[f"w{n}"] = f"%{w}%"
	rows = frappe.db.sql(
		"select i.name, i.item_name, i.stock_uom, i.item_group from tabItem i where "
		+ " and ".join(conds) + " order by i.item_name limit %(limit)s", args, as_dict=True)
	return [{"value": r.name, "item_name": r.item_name, "uom": r.stock_uom, "group": r.item_group,
	         "label": r.item_name if r.name == r.item_name else f"{r.item_name} · {r.name}"} for r in rows]


def match_all(dry_run=True):
	"""Create Livestock Sires from the distinct typed bulls and straw Items and link the records.

	Reads Livestock Event.sire (by event type) and Animal.sire_name; never rewrites
	the text. Reuses an existing Livestock Sire (same code, else same name) rather
	than making a second, so it is safe to run again. With dry_run it writes
	nothing and returns the proposal.
	"""
	rows = []
	for text, etype, c in frappe.db.sql(
		"select sire, event_type, count(*) from `tabLivestock Event` where ifnull(sire,'')!='' "
		"and ifnull(sire_link,'')='' group by sire, event_type"
	):
		rows.append((text, (etype or "event").lower(), c))
	for text, c in frappe.db.sql(
		"select sire_name, count(*) from `tabAnimal` where ifnull(sire_name,'')!='' "
		"and ifnull(sire_link,'')='' group by sire_name"
	):
		rows.append((text, "animal", c))
	sires, text_to_key = propose(rows, _straw_items())

	out, key_to_name = [], {}
	for s in sires:
		existing = (frappe.db.get_value("Livestock Sire", {"sire_code": s["code"]}, "name")
		            if s["code"] else None) or find(s["name"])
		item = primary_item(s["items"])
		counts = s["counts"]
		out.append({"name": s["name"], "code": s["code"], "label": label(s["name"], s["code"]),
		            "sire_type": "Semen", "semen_item": item, "items": s["items"],
		            "aliases": s["aliases"], "variants": s["variants"], "notes": s["notes"],
		            "services": counts.get("service", 0), "calvings": counts.get("calving", 0),
		            "events": sum(v for k, v in counts.items() if k != "animal"),
		            "animals": counts.get("animal", 0), "exists": existing})
		if dry_run:
			key_to_name[s["key"]] = existing or (s["code"] or s["name"])
			continue
		if not existing:
			doc = frappe.get_doc({"doctype": "Livestock Sire", "sire_name": s["name"],
			                      "sire_code": s["code"] or None, "sire_type": "Semen",
			                      "semen_item": item, "active": 1,
			                      "notes": "; ".join(s["notes"]) or None}).insert(ignore_permissions=True)
			existing = doc.name
		elif item and not frappe.db.get_value("Livestock Sire", existing, "semen_item"):
			frappe.db.set_value("Livestock Sire", existing, "semen_item", item)
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
		"with_item": sum(1 for s in out if s["semen_item"]),
		"to_create": sum(1 for s in out if not s["exists"]),
		"events_to_link": sum(s["events"] for s in out),
		"animals_to_link": sum(s["animals"] for s in out),
		"linked": None if dry_run else linked,
		"sires": out,
	}


def _straw_items():
	"""[(Item code, Item name)] of the semen straws: the Service groups' items when the
	event type names groups, else every Item whose name says semen or sexed."""
	try:
		from upande_livestock.serverscripts.common import event_items

		groups = event_items.groups_for_event("Service")
		filters = {"disabled": 0}
		if groups:
			filters["item_group"] = ["in", groups]
			rows = frappe.get_all("Item", filters=filters, fields=["name", "item_name"])
		else:
			rows = frappe.db.sql(
				"select name, item_name from tabItem where disabled=0 and "
				"(item_name like '%%semen%%' or item_name like '%%sexed%%')", as_dict=True)
		return [(r.name, r.item_name) for r in rows]
	except Exception:
		return []


def require_active(sire):
	"""The Livestock Sire name when it exists and is active; throws otherwise.

	A blank sire is fine (returns None). A picked sire that was deleted or
	switched off must not be recorded on a new service.
	"""
	sire = tidy(sire)
	if not sire:
		return None
	row = frappe.db.get_value("Livestock Sire", sire, ["active"], as_dict=True)
	if not row:
		frappe.throw(frappe._("{0} is not a Livestock Sire.").format(sire))
	if not row.active:
		frappe.throw(frappe._("{0} is not active; pick another sire.").format(sire))
	return sire
