# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What a buyer's quality sheet means: validation and the overall result.

The pure part (`clean`, `evaluate`) takes plain values and the farm's limits and
touches no database, so the rules can be tested without a site. `limits()` is the
only function here that reads Livestock Settings.

Which tests decide the result: the go / no-go ones the buyer reports — resazurin,
antibiotics, hydrogen peroxide, frothing — and aflatoxin M1 against a limit. The
composition figures (pH, TTA, SNF, protein, fat, SG, freezing point) are recorded
and shown but do not decide pass or fail: the farm has not given a threshold for
them, and inventing one would call good milk bad.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

DOCTYPE = "Milk Quality Test"

SAMPLE_TYPES = ("Bottle sample", "Tanker", "Can")
SHIFTS = ("Morning", "Afternoon", "Evening")

#: EU limit for aflatoxin M1 in milk is 50 ng/kg (= 50 ppt). Settings may change it.
DEFAULT_AFLATOXIN_LIMIT_PPT = 50.0
DEFAULT_RESAZURIN_MIN_SCORE = 4

#: field -> (label, low, high, decimals). A reading outside low..high is a typing
#: slip, not milk, and is refused rather than stored.
RANGES = {
	"quantity_l": ("Quantity", 0.001, 100000, 2),
	"receiving_temp_c": ("Receiving temperature", -5, 60, 1),
	"ph": ("pH", 0, 14, 2),
	"tta": ("TTA", 0, 30, 2),
	"snf_percent": ("SNF", 0, 20, 2),
	"freezing_point": ("Freezing point", -1.5, 0, 3),
	"specific_gravity": ("Specific gravity", 0.9, 1.2, 3),
	"protein_percent": ("Protein", 0, 15, 2),
	"butterfat_percent": ("Butterfat", 0, 20, 2),
	"aflatoxin_ppt": ("Aflatoxin M1", 0, 100000, 1),
}

#: Numeric readings; the test must have at least one of these or a result field.
NUMERIC_FIELDS = tuple(f for f in RANGES if f != "quantity_l")

CHOICES = {
	"sample_type": SAMPLE_TYPES,
	"shift": SHIFTS,
	"resazurin_result": ("Pass", "Fail"),
	"antibiotics": ("Negative", "Positive"),
	"hydrogen_peroxide": ("Nil", "Present"),
	"frothing": ("Pass", "Fail"),
}

ALIASES = {
	"-ve": "Negative", "negative": "Negative", "neg": "Negative", "+ve": "Positive",
	"positive": "Positive", "pos": "Positive", "nil": "Nil", "none": "Nil", "absent": "Nil",
	"present": "Present", "pass": "Pass", "fail": "Fail", "passed": "Pass", "failed": "Fail",
	"ok": "Pass",
}


def _blank(v):
	return v is None or (isinstance(v, str) and not v.strip())


def _number(field, v):
	try:
		return float(str(v).strip().replace(",", "."))
	except (TypeError, ValueError):
		frappe.throw(_("{0} must be a number.").format(RANGES[field][0]))


def limits():
	"""The farm's thresholds, read from Livestock Settings (defaults when unset).

	Read from tabSingles directly: an untouched site has no row, and
	get_single_value would call that 0 — which here means "off".
	"""

	def raw(field, default):
		row = frappe.db.sql(
			"select value from tabSingles where doctype='Livestock Settings' and field=%s", (field,)
		)
		v = row[0][0] if row else None
		return default if v in (None, "") else v

	return {
		"aflatoxin_limit_ppt": flt(raw("custom_quality_aflatoxin_limit_ppt", DEFAULT_AFLATOXIN_LIMIT_PPT)),
		"antibiotics_fail": bool(cint(raw("custom_quality_antibiotics_fail", 1))),
		"resazurin_min_score": cint(raw("custom_quality_resazurin_min_score", DEFAULT_RESAZURIN_MIN_SCORE)),
	}


def normalise_sensory(v):
	"""A signed whole number as text ("+1", "0", "-2"), or "" when not given."""
	if _blank(v):
		return ""
	text = str(v).strip().replace("−", "-")
	try:
		n = int(float(text))
		if float(text) != n:
			raise ValueError
	except ValueError:
		frappe.throw(_("Sensory score must be a whole number, such as +1, 0 or -1."))
	if abs(n) > 10:
		frappe.throw(_("Sensory score looks wrong: {0}.").format(text))
	return f"{n:+d}" if n else "0"


def clean(d: dict) -> dict:
	"""Validate and normalise a payload (or document fields) to canonical values.

	Returns only the keys it recognises. Raises (frappe.throw) on a bad value.
	"""
	out = {}
	for field, (label, low, high, dp) in RANGES.items():
		v = d.get(field)
		if _blank(v):
			out[field] = None
			continue
		n = _number(field, v)
		# A cold-tank freezing point is always below zero; a phone's number pad has
		# no minus key. A positive can only be that, so it is read as its negative.
		if field == "freezing_point" and n > 0:
			n = -n
		if field == "quantity_l" and n <= 0:
			frappe.throw(_("Quantity must be greater than zero."))
		if not (low <= n <= high):
			frappe.throw(_("{0} of {1} is outside the possible range ({2} to {3}).").format(label, n, low, high))
		out[field] = round(n, dp)

	for field, options in CHOICES.items():
		v = d.get(field)
		if _blank(v):
			out[field] = ""
			continue
		text = str(v).strip()
		text = ALIASES.get(text.lower(), text)
		match = next((o for o in options if o.lower() == text.lower()), None)
		if not match:
			frappe.throw(_("{0} must be one of: {1}.").format(field.replace("_", " ").capitalize(), ", ".join(options)))
		out[field] = match

	score = d.get("resazurin_score")
	if _blank(score):
		out["resazurin_score"] = ""
	else:
		try:
			n = int(float(str(score).strip()))
			if not 0 <= n <= 6 or float(str(score).strip()) != n:
				raise ValueError
		except ValueError:
			frappe.throw(_("Resazurin score must be a whole number from 0 to 6."))
		out["resazurin_score"] = str(n)

	out["sensory_score"] = normalise_sensory(d.get("sensory_score"))
	return out


def effective_resazurin(values: dict, lim: dict):
	"""'Pass' / 'Fail' / None. An explicit result wins; otherwise the score is
	judged against the farm's minimum (6 is clean milk, 0 is spoiled)."""
	if values.get("resazurin_result"):
		return values["resazurin_result"]
	score = values.get("resazurin_score")
	if score not in (None, ""):
		return "Pass" if cint(score) >= lim["resazurin_min_score"] else "Fail"
	return None


def checks(values: dict, lim: dict) -> dict:
	"""Each deciding test as 'pass', 'fail' or None (not recorded)."""
	res = effective_resazurin(values, lim)
	out = {
		"resazurin": None if res is None else res.lower(),
		"antibiotics": None,
		"hydrogen_peroxide": None,
		"frothing": None,
		"aflatoxin": None,
	}
	if values.get("antibiotics"):
		positive = values["antibiotics"] == "Positive"
		out["antibiotics"] = "fail" if positive and lim["antibiotics_fail"] else ("warn" if positive else "pass")
	if values.get("hydrogen_peroxide"):
		out["hydrogen_peroxide"] = "fail" if values["hydrogen_peroxide"] == "Present" else "pass"
	if values.get("frothing"):
		out["frothing"] = values["frothing"].lower()
	afla = values.get("aflatoxin_ppt")
	if afla not in (None, "") and flt(afla) > 0 and lim["aflatoxin_limit_ppt"] > 0:
		out["aflatoxin"] = "fail" if flt(afla) > lim["aflatoxin_limit_ppt"] else "pass"
	return out


LABELS = {
	"resazurin": "Resazurin",
	"antibiotics": "Antibiotics",
	"hydrogen_peroxide": "Hydrogen peroxide",
	"frothing": "Frothing",
	"aflatoxin": "Aflatoxin M1",
}


def evaluate(values: dict, lim: dict | None = None) -> dict:
	"""{overall, failed, checks}. Overall is Fail when any deciding test fails,
	Pass when at least one was recorded and none failed, else Not assessed."""
	lim = lim or limits()
	c = checks(values, lim)
	failed = [LABELS[k] for k, v in c.items() if v == "fail"]
	recorded = [v for v in c.values() if v]
	overall = "Fail" if failed else ("Pass" if recorded else "Not assessed")
	return {"overall": overall, "failed": failed, "checks": c}


def has_any_result(v: dict) -> bool:
	if any(v.get(f) is not None for f in NUMERIC_FIELDS):
		return True
	return any(
		v.get(f) for f in ("resazurin_score", "resazurin_result", "antibiotics", "hydrogen_peroxide", "frothing", "sensory_score")
	)


def check_date(value):
	if _blank(value):
		return today()
	if getdate(value) > getdate(today()):
		frappe.throw(_("The sample date cannot be in the future."))
	return str(getdate(value))
