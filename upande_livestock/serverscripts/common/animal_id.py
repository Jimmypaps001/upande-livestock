# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What an animal's number is, and who is allowed to have which one.

A039/26 is a heifer born in 2026, the thirty-ninth of her year. B013/26 is a
bull born in the same year — the two series run independently, which the farm's
own register proves: B013/26 through B024/26 sit alongside A002/26 through
A039/26.

The number IS the record name. That is a reversal of an earlier decision, which
refused it because four register entries are not numbers at all and ninety-two
animals had none, and "a naming scheme that cannot name every record is not a
naming scheme". The objection was right. `allocate` answers it: anything the
register cannot name is given the next free number in its birth year, so the
scheme now names everything.

`taken` reads Animal.name and nothing else. `Animal.book_number` keeps the
register's own words — including the entries that are not numbers — as evidence
of what the paper said, not as a second authority to disagree with this one.
"""

import re

import frappe
from frappe import _
from frappe.utils import getdate, today

PREFIX_BY_SEX = {"Female": "A", "Male": "B"}
PATTERN = re.compile(r"^([AB])(\d{3})/(\d{2})$")

# The register's two transcription habits: a letter O standing in for a zero —
# sometimes twice, as in BOO9/26 — and a backslash for the separator. The
# sequence is matched as "three characters that are digits or the letter O"
# rather than by enumerating where the O may fall, because the habit is
# "type O for zero", not a rule about position.
_SHAPE = re.compile(r"^([AB])([O0-9]{3})/(\d{2})$", re.I)

MAX_SEQ = 999


def prefix_for_sex(sex):
	"""The letter an animal of this sex is numbered under.

	Throws rather than defaulting: a calf whose sex never arrived would
	otherwise be silently numbered as a heifer and join the milking ladder.
	"""
	prefix = PREFIX_BY_SEX.get((sex or "").strip().title())
	if not prefix:
		frappe.throw(_("Sex must be Female or Male to give an animal a number — got {0}.").format(
			sex or "nothing"))
	return prefix


def format_id(prefix, seq, yy):
	"""A039/26 from its three parts."""
	return "{}{:03d}/{:02d}".format(prefix, int(seq), int(yy) % 100)


def parse(animal_id):
	"""The three parts of a number, or None when it is not one."""
	m = PATTERN.match((animal_id or "").strip().upper())
	if not m:
		return None
	yy = int(m.group(3))
	return {
		"prefix": m.group(1),
		"seq": int(m.group(2)),
		"yy": yy,
		"year": 2000 + yy,
		"id": m.group(0).upper(),
	}


def tidy(raw):
	"""Correct a register entry's transcription, without inventing one.

	A letter O wherever a zero belongs, and a backslash for the separator.
	Anything this cannot recognise comes back exactly as found — guessing at ELLA
	or 23:29 is how a wrong number becomes the record.
	"""
	b = (raw or "").strip().replace("\\", "/")
	m = _SHAPE.match(b)
	if not m:
		return b
	seq = m.group(2).upper().replace("O", "0")
	return "{}{}/{}".format(m.group(1).upper(), seq, m.group(3))


# A number the farm wrote into a display name — "BO05/26 (Bull)", "AO06/26 (Cow)".
# Anchored on a word boundary so it cannot pick a fragment out of a longer token.
_EMBEDDED = re.compile(r"(?:^|[^A-Z0-9])([AB][O0-9]{3}[/\\]\d{2})(?:$|[^0-9])", re.I)


def extract(text):
	"""The register number inside a piece of text, tidied, or "".

	Ten animals here were never given a book number but carry one in their
	display name, where somebody typed it because there was nowhere else to put
	it. Reading it back is not guesswork — it is the same string the register
	uses, in the wrong field.
	"""
	m = _EMBEDDED.search((text or "").upper())
	if not m:
		return ""
	out = tidy(m.group(1))
	return out if parse(out) else ""


def year_of(birth_date=None):
	"""The two-digit year a number born on this date belongs to."""
	return getdate(birth_date or today()).year % 100


def taken(prefix, yy):
	"""Every sequence already used in this prefix and year.

	Reads the record name, which is the number. A LIKE on an indexed primary key
	costs nothing and cannot disagree with itself.
	"""
	pattern = "{}___/{:02d}".format(prefix, int(yy) % 100)
	rows = frappe.get_all("Animal", filters=[["name", "like", pattern]], pluck="name",
	                      limit_page_length=0)
	out = set()
	for name in rows:
		got = parse(name)
		if got and got["prefix"] == prefix and got["yy"] == int(yy) % 100:
			out.add(got["seq"])
	return out


def next_free(prefix, yy, used=None):
	"""The number a new animal of this prefix and year should get.

	One past the high-water mark, not the lowest hole. A calf born today is the
	next one in the book; the holes are offered when somebody is correcting a
	number by hand, which is a different question.
	"""
	used = taken(prefix, yy) if used is None else used
	nxt = (max(used) + 1) if used else 1
	if nxt > MAX_SEQ:
		# Fall back into the holes rather than refuse a birth outright.
		holes = gaps(prefix, yy, limit=1, used=used)
		if not holes:
			frappe.throw(_("Every number from 001 to {0} is used for 20{1}.").format(MAX_SEQ, yy))
		return holes[0]
	return nxt


def gaps(prefix, yy, limit=12, used=None):
	"""Free numbers below the high-water mark, lowest first.

	Only below it: everything above is free, and listing it would bury the
	handful that are actually interesting.
	"""
	used = taken(prefix, yy) if used is None else used
	if not used:
		return []
	high = max(used)
	out = []
	for n in range(1, high):
		if n not in used:
			out.append(n)
			if len(out) >= limit:
				break
	return out


def describe_gaps(prefix, yy, limit=12, used=None):
	"""'25, 26, 28-31' — runs collapsed, because a list of forty reads as noise."""
	holes = gaps(prefix, yy, limit=limit, used=used)
	if not holes:
		return ""
	runs, start, prev = [], holes[0], holes[0]
	for n in holes[1:]:
		if n == prev + 1:
			prev = n
			continue
		runs.append((start, prev))
		start = prev = n
	runs.append((start, prev))
	return ", ".join(
		"{:03d}".format(a) if a == b else "{:03d}-{:03d}".format(a, b) for a, b in runs
	)


def allocate(sex, birth_date=None):
	"""The next number for an animal of this sex born on this date."""
	prefix = prefix_for_sex(sex)
	yy = year_of(birth_date)
	return format_id(prefix, next_free(prefix, yy), yy)


def assert_assignable(animal_id, sex, current=None):
	"""Throw unless this number can be given to this animal.

	Every message names what to do next — a farm worker correcting a number
	needs the free ones, not 'Validation Error'.
	"""
	got = parse(animal_id)
	if not got:
		frappe.throw(_("{0} is not an animal number. They look like A013/26 — "
		               "a letter, three digits, a slash, and the year of birth.").format(animal_id))

	prefix = prefix_for_sex(sex)
	if got["prefix"] != prefix:
		frappe.throw(_("{0} is numbered {1}, but {2} animals are numbered {3}.").format(
			animal_id, got["prefix"], (sex or "").lower(), prefix))

	this_year = getdate(today()).year
	if got["year"] > this_year:
		frappe.throw(_("{0} has not happened yet — an animal cannot be born in the future.").format(
			got["year"]))

	if got["seq"] < 1:
		frappe.throw(_("An animal's number starts at 001."))

	if current and got["id"] == (current or "").strip().upper():
		return got

	if frappe.db.exists("Animal", got["id"]):
		free = describe_gaps(got["prefix"], got["yy"])
		owner = frappe.db.get_value("Animal", got["id"], "burn_name") or got["id"]
		if free:
			frappe.throw(_("{0} already belongs to {1}. Free in 20{2}: {3}.").format(
				got["id"], owner, "{:02d}".format(got["yy"]), free))
		frappe.throw(_("{0} already belongs to {1}. Every number below it is used in 20{2}.").format(
			got["id"], owner, "{:02d}".format(got["yy"])))

	return got
