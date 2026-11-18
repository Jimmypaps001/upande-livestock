# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Read a Gallagher weigh-scale session file and record its weights.

The scale at the crush exports one file per session: a row per animal through
the race with its visual tag (VID), its electronic ear tag (EID), the day and
time, and the live weight. Typing those back in by hand is how weighings went
unrecorded, so the file is read as it comes off the scale.

TWO CALLS, ONE ANALYSIS. `preview` reads the file and says what it holds: the
days it covers, which rows found their animal and which did not, which were
already recorded, and which animals on the farm did not go through at all.
Nothing is written. `commit` reads the same file again, runs the same analysis,
and records exactly the rows the preview called ready. The browser holds the
file between the two, so the server keeps no state and a stale preview cannot
record something the file does not say.

MATCHING. The EID is what the scale reads off the animal, so it wins when it
names exactly one animal on the farm. The VID is what a person typed into the
scale, matched against the burn name, tag number, book number and name, with
leading zeros ignored (the scale writes 0053 for tag 53). A row whose EID and
VID name two different animals is not recorded: one of them is wrong, and a
weight on the wrong cow is worse than a weight left out.

AN IMPORT IS HISTORY WITH ITS OWN DATE. A session is always read in after the
weighing, so the rows are recorded against the scale's own day even while the
backdating window is closed (a server flag that record_one honours; the
records are still stamped as backdated). A future date is never recorded.

DATE ORDER. A slash date such as 9/15/2026 or 03/04/2026 is month-first or
day-first. It is decided once per file, never row by row: day-first when any
first number is above 12, month-first when any second number is above 12, and
month-first when the file cannot say (what Mutara's scale exports). A file that
shows both (15/3/2026 and 3/15/2026) contradicts itself and is refused. The
preview says which order was used and whether the file settled it, and the
`date_order` param ("auto" | "mdy" | "dmy") overrides it.
"""

import base64
import csv
import io
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import frappe
from frappe import _
from frappe.utils import cstr, flt, formatdate, getdate, today

from upande_livestock.serverscripts.common.choices import herd_label_map, is_active
from upande_livestock.serverscripts.common.envelope import as_dict, guard, guard_read, run
from upande_livestock.serverscripts.weights.create_weight_record import record_one

#: The cap on a file read in one request. A long session is a few hundred rows
#: and well under 100 KB; anything this big is not a scale export.
MAX_BYTES = 5 * 1024 * 1024

#: One name reused for every row, as record_weights does.
SAVEPOINT = "livestock_gallagher_row"

#: What a Gallagher crush scale is, among the methods the record offers.
DEFAULT_METHOD = "Platform Scale"

#: Header spellings, squeezed to lower-case letters and digits, and the column
#: each one is. Gallagher's own headings first, then the obvious variants a
#: person re-saving the file in Excel might leave behind.
HEADERS = {
	"vid": "vid",
	"visualid": "vid",
	"visualtag": "vid",
	"eid": "eid",
	"electronicid": "eid",
	"rfid": "eid",
	"nlis": "nlis",
	"date": "date",
	"time": "time",
	"draft": "draft",
	"notes": "notes",
	"note": "notes",
	"liveweight": "weight",
	"liveweightkg": "weight",
	"weight": "weight",
	"weightkg": "weight",
	"averagedailygain": "adg",
	"overalldailygain": "odg",
}

#: What the scale writes in the VID box for "no visual tag".
BLANK_TAGS = {"", "NA", "N/A", "-", "NONE", "NIL"}

#: The orders a slash date can be read in, and "auto" (decide from the file).
DATE_ORDERS = ("auto", "mdy", "dmy")
_SLASH_DATE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$")

READY = "ready"
ALREADY = "already_recorded"
REPEAT = "repeat"
UNMATCHED = "unmatched"
INVALID = "invalid"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def preview(payload):
	"""Read a scale file and say what it holds. Writes nothing.

	payload: {filename, content (base64) | file_url, herds?: [herd, ...],
	date_order?: "auto" | "mdy" | "dmy"}
	"""

	def go():
		guard_read("Livestock Weight Record")
		d = as_dict(payload)
		return public(analyse(*load_file(d), herds=d.get("herds"), date_order=d.get("date_order")))

	return run(go, "livestock gallagher preview failed")


@frappe.whitelist()
def commit(payload):
	"""Record every row the preview of the same file calls ready.

	payload: {filename, content (base64) | file_url, method?, herds?, date_order?}
	"""

	def go():
		guard("Livestock Weight Record")
		d = as_dict(payload)
		filename, content = load_file(d)
		found = analyse(filename, content, herds=d.get("herds"), date_order=d.get("date_order"))
		return record(found, method=d.get("method"), filename=filename)

	return run(go, "livestock gallagher commit failed")


# ---------------------------------------------------------------------------
# Reading the file
# ---------------------------------------------------------------------------


def load_file(d):
	"""(filename, bytes) from a base64 body or an attached File."""
	filename = cstr(d.get("filename")).strip()
	if d.get("file_url"):
		name = frappe.db.get_value("File", {"file_url": d["file_url"]}, "name")
		if not name:
			frappe.throw(_("That file is no longer on the site. Upload it again."))
		file = frappe.get_doc("File", name)
		if not frappe.has_permission("File", "read", doc=file):
			frappe.throw(_("You are not permitted to read that file."), frappe.PermissionError)
		content = file.get_content()
		filename = filename or file.file_name or ""
	elif d.get("content"):
		raw = cstr(d["content"])
		if "," in raw[:100] and raw.startswith("data:"):
			raw = raw.split(",", 1)[1]
		try:
			content = base64.b64decode(raw, validate=False)
		except Exception:
			frappe.throw(_("The file did not arrive whole. Choose it again."))
	else:
		frappe.throw(_("Choose a Gallagher file to import."))
	if isinstance(content, str):
		content = content.encode("utf-8")
	if not content:
		frappe.throw(_("The file is empty."))
	if len(content) > MAX_BYTES:
		frappe.throw(_("The file is larger than a weighing session can be. Check it is the scale's export."))
	return filename, content


def read_table(content):
	"""The file as rows of cell values, and the format it was read as."""
	if content[:4] == b"PK\x03\x04":
		from openpyxl import load_workbook

		try:
			book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
		except Exception:
			frappe.throw(_("The Excel file could not be opened. Save it again from Excel and retry."))
		sheet = book.worksheets[0]
		return [list(r) for r in sheet.iter_rows(values_only=True)], "xlsx"
	if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
		import xlrd

		try:
			book = xlrd.open_workbook(file_contents=content)
		except Exception:
			frappe.throw(_("The Excel file could not be opened. Save it again from Excel and retry."))
		sheet = book.sheet_by_index(0)
		rows = []
		for i in range(sheet.nrows):
			row = []
			for cell in sheet.row(i):
				if cell.ctype == xlrd.XL_CELL_DATE:
					row.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
				else:
					row.append(cell.value)
			rows.append(row)
		return rows, "xls"

	for encoding in ("utf-8-sig", "cp1252", "latin-1"):
		try:
			text = content.decode(encoding)
			break
		except UnicodeDecodeError:
			continue
	if text.lstrip()[:1] == "<":
		frappe.throw(_("This file is a web page, not a scale export. Save it from Excel as CSV or .xlsx and retry."))
	first = text.split("\n", 1)[0]
	delimiter = max((",", ";", "\t"), key=first.count)
	return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)], "csv"


def _squeeze(value):
	return re.sub(r"[^a-z0-9]", "", cstr(value).lower())


def find_header(table):
	"""(index of the header row, {column: position}).

	The header is the first row that names a weight and an ID column; a
	re-saved file sometimes carries a title line or two above it.
	"""
	for i, row in enumerate(table[:20]):
		columns = {}
		for pos, cell in enumerate(row):
			key = HEADERS.get(_squeeze(cell))
			if key and key not in columns:
				columns[key] = pos
		if "weight" in columns and ("vid" in columns or "eid" in columns):
			return i, columns
	frappe.throw(
		_(
			"This file has no Live Weight column with a VID or EID beside it. "
			"Export the session from the Gallagher as CSV or Excel and try again."
		)
	)


def parse_date(value, order="mdy"):
	"""A date from a Gallagher cell. The scale writes month first: 9/15/2026.

	`order` ("mdy" or "dmy") reads a slash date; it is decided once per file
	(`decide_date_order`), not guessed per row.
	"""
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	if isinstance(value, (int, float)) and not isinstance(value, bool):
		# An Excel serial day number.
		if 20000 < value < 80000:
			return date(1899, 12, 30) + timedelta(days=int(value))
		return None
	s = cstr(value).strip().split(" ")[0].split("T")[0]
	if not s:
		return None
	try:
		m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
		if m:
			return date(int(m[1]), int(m[2]), int(m[3]))
		m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$", s)
		if m:
			a, b, y = int(m[1]), int(m[2]), int(m[3])
			if y < 100:
				y += 2000
			month, day = (a, b) if order != "dmy" else (b, a)
			return date(y, month, day)
	except ValueError:
		return None
	return None


def parse_time(value):
	"""HH:MM:SS, or "" when the file has no time."""
	if isinstance(value, datetime):
		value = value.time()
	if isinstance(value, time):
		return value.strftime("%H:%M:%S")
	if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 1:
		seconds = int(round(value * 86400))
		return "%02d:%02d:%02d" % (seconds // 3600, seconds % 3600 // 60, seconds % 60)
	s = cstr(value).strip()
	m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
	if not m:
		return ""
	return "%02d:%02d:%02d" % (int(m[1]), int(m[2]), int(m[3] or 0))


def _cell_text(value):
	if isinstance(value, float) and value.is_integer():
		value = int(value)
	return cstr(value).strip()


def norm_tag(value):
	"""A visual tag as it is compared: no spaces, upper case, no leading zeros."""
	s = re.sub(r"\s+", "", _cell_text(value)).upper()
	if s in BLANK_TAGS:
		return ""
	return s.lstrip("0") or s


def norm_eid(value):
	"""An electronic tag as it is compared: its digits, when there are enough
	of them to be one (an ISO ear tag is fifteen)."""
	digits = re.sub(r"\D", "", _cell_text(value))
	return digits if len(digits) >= 12 else ""


def decide_date_order(texts, asked="auto"):
	"""{"used", "asked", "settled", "day_first_rows", "month_first_rows"} for a file.

	Looks at every slash date in the file: a first number above 12 can only be a
	day, a second number above 12 can only be a day the other way round. Both in
	one file means the file contradicts itself and is refused.
	"""
	asked = asked if asked in DATE_ORDERS else "auto"
	dmy = mdy = 0
	for t in texts:
		m = _SLASH_DATE.match(cstr(t).strip().split(" ")[0])
		if not m:
			continue
		a, b = int(m[1]), int(m[2])
		if a > 12 and b <= 12:
			dmy += 1
		elif b > 12 and a <= 12:
			mdy += 1
	if dmy and mdy:
		frappe.throw(
			_(
				"The dates in this file contradict each other: {0} rows can only be day first (like 15/3/2026) and {1} can only be month first (like 3/15/2026). Fix the file, or export the session again, before importing it."
			).format(dmy, mdy)
		)
	settled = bool(dmy or mdy)
	if asked != "auto":
		used = asked
	elif dmy:
		used = "dmy"
	else:
		used = "mdy"
	return {"used": used, "asked": asked, "settled": settled, "day_first_rows": dmy, "month_first_rows": mdy}


def parse_rows(table, date_order="auto", info=None):
	"""The data rows below the header, each a dict. Blank rows are dropped.

	The date order is decided once from every date in the file; pass a dict as
	`info` to receive the decision (see `decide_date_order`).
	"""
	head, columns = find_header(table)

	def cell(row, key):
		pos = columns.get(key)
		return row[pos] if pos is not None and pos < len(row) else None

	data = [(i, row) for i, row in enumerate(table[head + 1 :], start=head + 2) if any(_cell_text(c) for c in row)]
	decision = decide_date_order(
		[cell(row, "date") for _i, row in data if isinstance(cell(row, "date"), str)], date_order
	)
	if info is not None:
		info.update(decision)
	rows = []
	for i, row in data:
		raw_date = cell(row, "date")
		vid = _cell_text(cell(row, "vid"))
		eid = _cell_text(cell(row, "eid"))
		rows.append({
			"row": i,
			"vid": "" if vid.upper() in BLANK_TAGS else vid,
			"eid": eid,
			"date": parse_date(raw_date, decision["used"]),
			"date_text": _cell_text(raw_date),
			"time": parse_time(cell(row, "time")),
			"weight_kg": flt(re.sub(r"[^0-9.\-]", "", _cell_text(cell(row, "weight"))) or 0),
			"notes": _cell_text(cell(row, "notes")),
		})
	return rows


# ---------------------------------------------------------------------------
# Matching and checking
# ---------------------------------------------------------------------------


def animal_index():
	"""Every animal, and the two lookups a row is matched through."""
	rows = frappe.db.sql(
		"""select name, tag_number, burn_name, book_number, eid, status, disabled, current_herd
		   from `tabAnimal` where docstatus < 2""",
		as_dict=True,
	)
	animals = {r.name: r for r in rows}
	by_eid, by_vid = defaultdict(set), defaultdict(set)
	for r in rows:
		for v in (r.eid, r.tag_number, r.name):
			key = norm_eid(v)
			if key:
				by_eid[key].add(r.name)
		for v in (r.burn_name, r.tag_number, r.book_number, r.name):
			key = norm_tag(v)
			if key:
				by_vid[key].add(r.name)
	return animals, by_eid, by_vid


def _label(a):
	return a.burn_name or a.tag_number or a.name


def _pick(names, animals):
	"""(animal, problem) from the animals a key names.

	One active animal is a match. Several active ones is ambiguous. Only
	retired ones is a match to say no to.
	"""
	if not names:
		return None, None
	active = sorted(n for n in names if is_active(animals[n]))
	if len(active) == 1:
		return active[0], None
	if len(active) > 1:
		return None, ("ambiguous", active)
	return None, ("retired", sorted(names))


def match_row(r, animals, by_eid, by_vid):
	"""(animal, matched_by, why). `animal` is None when the row stays out."""
	eid, vid = norm_eid(r["eid"]), norm_tag(r["vid"])
	if not eid and not vid:
		return None, None, _("No VID or EID on this row, so it cannot be put to an animal.")
	by_e, e_problem = _pick(by_eid.get(eid), animals) if eid else (None, None)
	by_v, v_problem = _pick(by_vid.get(vid), animals) if vid else (None, None)

	if by_e:
		if by_v and by_v != by_e:
			return None, None, _("The EID belongs to {0} but the VID {1} belongs to {2}. Fix the tag before importing this row.").format(
				_label(animals[by_e]), r["vid"], _label(animals[by_v])
			)
		return by_e, "eid", None
	if by_v:
		return by_v, "vid", None

	for problem in (e_problem, v_problem):
		if problem and problem[0] == "retired":
			a = animals[problem[1][0]]
			return None, None, _("{0} is {1} and no longer on the farm.").format(
				_label(a), _(a.status or "retired")
			)
	if v_problem and v_problem[0] == "ambiguous":
		return None, None, _("VID {0} is on more than one animal on the farm ({1}) and the EID did not settle which.").format(
			r["vid"], ", ".join(_label(animals[n]) for n in v_problem[1])
		)
	return None, None, _("No animal on the farm has VID {0} or EID {1}.").format(
		r["vid"] or _("(blank)"), r["eid"] or _("(blank)")
	)


def _last_weights(animal_names):
	"""{animal: (last weight date, last weight kg)} from submitted records."""
	if not animal_names:
		return {}
	rows = frappe.db.sql(
		"""select w.animal, w.weight_date, w.weight_kg
		   from `tabLivestock Weight Record` w
		   join (select animal, max(weight_date) d from `tabLivestock Weight Record`
		         where docstatus = 1 and animal in %(a)s group by animal) m
		     on m.animal = w.animal and m.d = w.weight_date
		   where w.docstatus = 1
		   order by w.creation desc""",
		{"a": tuple(animal_names)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.animal, (r.weight_date, flt(r.weight_kg)))
	return out


def _recorded_on(pairs):
	"""{(animal, date): weight} already recorded, for the pairs asked about."""
	if not pairs:
		return {}
	animals = tuple({a for a, _d in pairs})
	dates = tuple({d for _a, d in pairs})
	rows = frappe.db.sql(
		"""select animal, weight_date, weight_kg from `tabLivestock Weight Record`
		   where docstatus = 1 and animal in %(a)s and weight_date in %(d)s""",
		{"a": animals, "d": dates},
		as_dict=True,
	)
	return {(r.animal, getdate(r.weight_date)): flt(r.weight_kg) for r in rows}


def analyse(filename, content, herds=None, date_order="auto"):
	"""Everything the preview shows, and the rows commit records."""
	table, fmt = read_table(content)
	order = {}
	rows = parse_rows(table, date_order, order)
	if not rows:
		frappe.throw(_("The file has a header but no weighings under it."))

	animals, by_eid, by_vid = animal_index()
	labels = herd_label_map()
	now = getdate(today())

	for r in rows:
		r["animal"], r["matched_by"], why = match_row(r, animals, by_eid, by_vid)
		r["why"] = why
		if not r["date"]:
			r["status"], r["why"] = INVALID, _("The date {0} could not be read.").format(r["date_text"] or _("(blank)"))
		elif r["date"] > now:
			r["status"], r["why"] = INVALID, _("Weighed on {0}, which is in the future.").format(formatdate(r["date"]))
		elif not r["animal"]:
			r["status"] = UNMATCHED
		elif r["weight_kg"] <= 0:
			r["status"], r["why"] = INVALID, _("No weight on this row.")
		else:
			r["status"] = READY

	# The same animal twice on one day: the later reading is the one that
	# stands (a cow put back on the scale because the first reading was off).
	# The scale lists newest first, so without times the first row is latest.
	seen = defaultdict(list)
	for r in rows:
		if r["status"] == READY:
			seen[(r["animal"], r["date"])].append(r)
	for group in seen.values():
		if len(group) < 2:
			continue
		keep = max(group, key=lambda x: (x["time"], -x["row"]))
		for r in group:
			if r is not keep:
				r["status"] = REPEAT
				r["why"] = _("{0} was weighed again on this day (row {1}); that reading is the one recorded.").format(
					_label(animals[r["animal"]]), keep["row"]
				)

	matched = {r["animal"] for r in rows if r["animal"]}
	recorded = _recorded_on({(r["animal"], r["date"]) for r in rows if r["status"] == READY})
	for r in rows:
		if r["status"] == READY and (r["animal"], r["date"]) in recorded:
			r["status"] = ALREADY
			r["why"] = _("{0} kg is already recorded for {1} on {2}.").format(
				recorded[(r["animal"], r["date"])], _label(animals[r["animal"]]), formatdate(r["date"])
			)

	last = _last_weights(
		{n for n, a in animals.items() if is_active(a)} | matched
	)
	for r in rows:
		a = animals.get(r["animal"]) if r["animal"] else None
		r["label"] = _label(a) if a else ""
		r["herd"] = a.current_herd if a else ""
		r["herd_label"] = labels.get(r["herd"] or "", r["herd"] or "") if a else ""
		lw = last.get(r["animal"]) if a else None
		r["last_weight_date"] = str(lw[0]) if lw else None
		r["last_weight_kg"] = lw[1] if lw else None
		r["older_than_last"] = bool(
			lw and r["date"] and r["status"] == READY and r["date"] < getdate(lw[0])
		)

	dates = _date_check(rows)
	scope = [h for h in (herds or []) if h]
	herd_rows, not_weighed = _not_weighed(animals, matched, last, labels, scope)

	def count(status):
		return sum(1 for r in rows if r["status"] == status)

	in_scope_active = sum(h["active"] for h in herd_rows if not scope or h["herd"] in scope)
	in_scope_weighed = sum(h["weighed"] for h in herd_rows if not scope or h["herd"] in scope)
	return {
		"ok": True,
		"file": {"name": filename, "format": fmt, "rows": len(rows)},
		"dates": dates,
		"date_order": order,
		"summary": {
			"rows": len(rows),
			"matched_rows": sum(1 for r in rows if r["animal"]),
			"matched_animals": len(matched),
			"unmatched_rows": count(UNMATCHED),
			"invalid_rows": count(INVALID),
			"to_record": count(READY),
			"already_recorded": count(ALREADY),
			"repeats": count(REPEAT),
			"active_animals": in_scope_active,
			"weighed_active": in_scope_weighed,
			"not_weighed": len(not_weighed),
		},
		"rows": [_row_out(r) for r in rows],
		"unmatched": [_row_out(r) for r in rows if r["status"] in (UNMATCHED, INVALID)],
		"herds": herd_rows,
		"scope_herds": scope,
		"not_weighed": not_weighed,
		"default_method": DEFAULT_METHOD,
		"_rows": rows,
		"_animals": animals,
		"_by_eid": by_eid,
	}


def public(found):
	"""The analysis without the working state commit needs."""
	return {k: v for k, v in found.items() if not k.startswith("_")}


def _row_out(r):
	return {
		"row": r["row"],
		"vid": r["vid"],
		"eid": r["eid"],
		"date": str(r["date"]) if r["date"] else None,
		"date_text": r["date_text"],
		"time": r["time"],
		"weight_kg": r["weight_kg"],
		"notes": r["notes"],
		"animal": r["animal"],
		"label": r["label"],
		"herd": r["herd"],
		"herd_label": r["herd_label"],
		"matched_by": r["matched_by"],
		"status": r["status"],
		"why": r["why"],
		"last_weight_date": r["last_weight_date"],
		"older_than_last": r["older_than_last"],
	}


def _date_check(rows):
	per_date = defaultdict(int)
	for r in rows:
		if r["date"]:
			per_date[r["date"]] += 1
	days = sorted(per_date)
	notes = []
	if len(days) > 1:
		notes.append(
			_("This file holds weighings from {0} different days, {1} to {2}. A session is normally one day: check it is the file you meant.").format(
				len(days), formatdate(days[0]), formatdate(days[-1])
			)
		)
	unreadable = [r for r in rows if not r["date"]]
	if unreadable:
		notes.append(_("{0} rows have a date that could not be read and will not be imported.").format(len(unreadable)))
	future = [r for r in rows if r["date"] and r["date"] > getdate(today())]
	if future:
		notes.append(_("{0} rows are dated in the future and will not be imported.").format(len(future)))
	older = [r for r in rows if r["older_than_last"]]
	if older:
		notes.append(
			_("{0} animals already have a later weight than the one in this file. Their weights will be recorded as history and their latest weight stays as it is.").format(
				len(older)
			)
		)
	repeats = [r for r in rows if r["status"] == REPEAT]
	if repeats:
		notes.append(_("{0} animals appear more than once on the same day. Only the latest reading of each is recorded.").format(len(repeats)))
	already = [r for r in rows if r["status"] == ALREADY]
	if already:
		notes.append(_("{0} weights are already recorded for that animal on that day and will be skipped.").format(len(already)))

	def ref(r):
		return {
			"row": r["row"], "vid": r["vid"], "eid": r["eid"], "animal": r["animal"], "label": r["label"],
			"date": str(r["date"]) if r["date"] else r["date_text"], "last_weight_date": r["last_weight_date"],
		}

	# The same animal on more than one day of one file: legitimate (two
	# sessions exported together) but worth a look.
	days_by_animal = defaultdict(set)
	for r in rows:
		if r["animal"] and r["date"]:
			days_by_animal[r["animal"]].add(r["date"])
	return {
		"from": str(days[0]) if days else None,
		"to": str(days[-1]) if days else None,
		"per_date": [{"date": str(d), "rows": per_date[d]} for d in days],
		"mixed": len(days) > 1,
		"unreadable": len(unreadable),
		"future": [ref(r) for r in future],
		"older_than_last": [ref(r) for r in older],
		"repeats": [ref(r) for r in repeats],
		"already_recorded": [ref(r) for r in already],
		"on_several_days": sorted(
			next(r["label"] for r in rows if r["animal"] == a)
			for a, d in days_by_animal.items()
			if len(d) > 1
		),
		"notes": notes,
	}


def _not_weighed(animals, matched, last, labels, scope):
	"""Per-herd counts for every herd with active animals, and the active
	animals that did not go through (in the chosen herds, or the whole farm)."""
	per_herd = defaultdict(lambda: {"active": 0, "weighed": 0})
	missing = []
	for name, a in animals.items():
		if not is_active(a):
			continue
		herd = a.current_herd or ""
		per_herd[herd]["active"] += 1
		if name in matched:
			per_herd[herd]["weighed"] += 1
			continue
		if scope and herd not in scope:
			continue
		lw = last.get(name)
		missing.append({
			"animal": name,
			"label": _label(a),
			"tag": a.tag_number or "",
			"herd": herd,
			"herd_label": labels.get(herd, herd) or _("No herd"),
			"last_weight_date": str(lw[0]) if lw else None,
			"last_weight_kg": lw[1] if lw else None,
		})
	missing.sort(key=lambda m: (m["herd_label"], m["label"]))
	herd_rows = sorted(
		(
			{
				"herd": h,
				"label": labels.get(h, h) or _("No herd"),
				"active": c["active"],
				"weighed": c["weighed"],
				"not_weighed": c["active"] - c["weighed"],
				"in_file": c["weighed"] > 0,
			}
			for h, c in per_herd.items()
		),
		key=lambda h: (not h["in_file"], h["label"]),
	)
	return herd_rows, missing


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def _method(asked):
	from upande_livestock.serverscripts.common.choices import select_options

	methods = select_options("Livestock Weight Record", "method")
	for m in (asked, DEFAULT_METHOD):
		if m and m in methods:
			return m
	return methods[0] if methods else None


def record(found, method=None, filename=""):
	"""Write the ready rows, one savepoint each, and fill in missing EIDs."""
	rows, animals, by_eid = found["_rows"], found["_animals"], found["_by_eid"]
	method = _method(method)
	done, failed = [], []
	skipped = [
		{"row": r["row"], "animal": r["animal"], "label": r["label"], "status": r["status"], "why": r["why"]}
		for r in rows
		if r["status"] != READY
	]
	frappe.flags.livestock_scale_import = True
	try:
		for r in rows:
			if r["status"] != READY:
				continue
			frappe.db.savepoint(SAVEPOINT)
			try:
				# One animal at a time: a second commit of the same file waits
				# here, then finds the weight already recorded and stands down.
				frappe.db.get_value("Animal", r["animal"], "name", for_update=True)
				if _recorded_on({(r["animal"], r["date"])}):
					skipped.append(
						{"row": r["row"], "animal": r["animal"], "label": r["label"], "status": ALREADY,
						 "why": _("Already recorded for {0} on {1}.").format(r["label"], formatdate(r["date"]))}
					)
					continue
				result = record_one({
					"animal": r["animal"],
					"event_date": str(r["date"]),
					"weight_kg": r["weight_kg"],
					"method": method,
					"remarks": _("Gallagher scale file {0}, row {1}{2}.").format(
						filename or _("(unnamed)"), r["row"], f", {r['time']}" if r["time"] else ""
					),
				})
				done.append({"row": r["row"], "animal": r["animal"], "label": r["label"], "name": result.get("name")})
			except Exception as e:
				frappe.db.rollback(save_point=SAVEPOINT)
				frappe.clear_last_message()
				failed.append({"row": r["row"], "animal": r["animal"], "label": r["label"], "why": str(e) or _("refused")})
	finally:
		frappe.flags.livestock_scale_import = False

	eids = _fill_eids(rows, animals, by_eid, {d["row"] for d in done})
	return {
		"ok": True,
		"recorded": len(done),
		"already_recorded": sum(1 for s in skipped if s["status"] == ALREADY),
		"not_recorded": len(skipped),
		"failed": failed,
		"skipped": skipped,
		"done": done,
		"eids_filled": eids,
		"method": method,
	}


def _fill_eids(rows, animals, by_eid, recorded_rows):
	"""Give an animal the EID the scale read off her, when she has none yet and
	no other animal carries it.

	Only from rows that were actually recorded, and only for a user who may
	write Animal (the write below skips permissions).
	"""
	if not frappe.has_permission("Animal", "write"):
		return 0
	filled = 0
	for r in rows:
		if r["row"] not in recorded_rows:
			continue
		eid = norm_eid(r["eid"])
		a = animals[r["animal"]]
		if not eid or a.eid:
			continue
		if frappe.db.get_value("Animal", r["animal"], "eid", for_update=True):
			continue
		if by_eid.get(eid, set()) - {r["animal"]}:
			continue
		text = re.sub(r"\s+", " ", r["eid"].strip())
		frappe.db.set_value("Animal", r["animal"], "eid", text, update_modified=False)
		a.eid = text
		by_eid[eid].add(r["animal"])
		filled += 1
	return filled
