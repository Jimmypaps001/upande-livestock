# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Weight-based appreciation of an animal's fixed asset.

Every animal is an ERPNext Asset (`Animal.asset_link`). ERPNext can depreciate
an asset but has no "appreciation" document; the ERP way to revalue is the
**Asset Value Adjustment** (AVA). Submitting one posts a Journal Entry between
the asset category's fixed-asset account and the *difference account* we give
it, sets the asset's `value_after_depreciation` to the new value and, when the
asset depreciates, reschedules the remaining depreciation. It works on assets
with or without depreciation, and it allows both increases (credit the
difference account) and decreases (debit it). The Herd category is a
non-depreciable one, so no depreciation accounts are needed.

How a value is arrived at:

    latest weight  x  price per kg of the first matrix row that fits the animal

The matrix is the "Appreciation Matrix" table of Livestock Settings, one row
per band (calf, weaner, heifer, in-calf heifer, cow, bull) and optionally an
age range and a weight range. A row can cap the value and can stop appreciating
at an age or at the first calving. Rows are tried in table order; put the
specific ones first.

BANDS are worked out here and are deliberately plain:

    male    < 6 months Calf, < 12 Weaner, else Bull
    female  < 6 months Calf, < 12 Weaner; then Heifer, In-calf Heifer when
            pregnant, Cow once she has calved

PUBLIC FUNCTIONS (single source of "what is this animal worth"):

* `appraise(animal)`            value from the matrix + the basis used.
* `current_value(animal)`       what to quote as the animal's value now:
                                the asset's book value (which this module keeps
                                in line with the appraisal), falling back to the
                                appraisal when there is no asset. Other
                                features (bull economics) should call this.
* `post_appreciation(animal, dry_run=1)`  one animal -> AVA.
* `run_appreciation(dry_run=0)` every Active/Dry animal with an asset.
* `run_if_due()`                the hourly scheduler entry point.

The whitelisted wrappers live in serverscripts/appreciation/.

IDEMPOTENT PER WEIGHING: each AVA carries `livestock_weight_ref` (the Weight
Record it was priced from). A weighing that already has a submitted AVA on the
asset is never posted again, so a second run, or a retry after a crash, is a
no-op. Re-pricing the matrix therefore takes effect with the next weighing.

DISPOSED ANIMALS ARE NEVER TOUCHED: a Sold/Scrapped/Capitalized asset, one with
a disposal date, or an animal whose status is not Active/Dry is skipped.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, today

SETTINGS = "Livestock Settings"
MATRIX = "appreciation_matrix"
LIVE_ANIMAL = ("Active", "Dry")
#: Asset statuses that may still be revalued.
LIVE_ASSET = ("Submitted", "Partially Depreciated", "Fully Depreciated")
WEANER_MONTHS = 6
HEIFER_MONTHS = 12
LAST_RUN_KEY = "livestock_appreciation_last_run"
WEEKLY_DAY = 0  # Monday


# --------------------------------------------------------------------------- settings


def settings():
	return frappe.get_single(SETTINGS)


def is_enabled(s=None):
	return bool(cint((s or settings()).get("appreciation_enabled")))


# --------------------------------------------------------------------------- animal facts


def age_months(animal, on=None):
	dob = animal.get("date_of_birth")
	if not dob:
		return None
	on = getdate(on or today())
	dob = getdate(dob)
	return (on.year - dob.year) * 12 + (on.month - dob.month) - (1 if on.day < dob.day else 0)


def has_calved(animal):
	return bool(animal.get("last_calving_date") or cint(animal.get("parity")))


def band_of(animal, months):
	"""Calf / Weaner / Heifer / In-calf Heifer / Cow / Bull, or None without a date of birth."""
	if months is None:
		return None
	if animal.get("sex") == "Male":
		if months < WEANER_MONTHS:
			return "Calf"
		return "Weaner" if months < HEIFER_MONTHS else "Bull"
	if months < WEANER_MONTHS:
		return "Calf"
	if months < HEIFER_MONTHS:
		return "Weaner"
	if has_calved(animal):
		return "Cow"
	return "In-calf Heifer" if animal.get("repro_status") == "Pregnant" else "Heifer"


def latest_weight(animal_name):
	"""(kg, date, ref) of the newest weighing, or None.

	The newest non-cancelled Weight Record; failing that the figure on the
	Animal itself, which has no date and is keyed by its value.
	"""
	rec = frappe.get_all(
		"Livestock Weight Record",
		filters={"animal": animal_name, "docstatus": ["<", 2], "weight_kg": [">", 0]},
		fields=["name", "weight_kg", "weight_date"],
		order_by="weight_date desc, creation desc",
		limit=1,
	)
	if rec:
		return flt(rec[0].weight_kg), rec[0].weight_date, rec[0].name
	kg = flt(frappe.db.get_value("Animal", animal_name, "last_weight_kg"))
	if kg > 0:
		return kg, None, f"animal:{kg:g}"
	return None


# --------------------------------------------------------------------------- matrix


def matching_row(rows, band, sex, months, weight):
	"""The first row (table order) that fits, or None. Rows priced at 0 never match."""
	for row in rows:
		if flt(row.get("price_per_kg")) <= 0:
			continue
		if row.get("band") and row.band != band:
			continue
		if row.get("sex") and row.sex != sex:
			continue
		lo, hi = cint(row.get("age_from_months")), cint(row.get("age_to_months"))
		if lo or hi:
			if months is None or months < lo or (hi and months >= hi):
				continue
		wlo, whi = flt(row.get("weight_from_kg")), flt(row.get("weight_to_kg"))
		if (wlo and weight < wlo) or (whi and weight >= whi):
			continue
		return row
	return None


def value_for(row, weight):
	"""(value, capped) for `weight` kg on a matrix row."""
	value = flt(weight) * flt(row.price_per_kg)
	cap = flt(row.get("max_value"))
	if cap and value > cap:
		return cap, True
	return value, False


def appraise(animal, on=None, s=None):
	"""What the matrix says this animal is worth now.

	Returns a dict: `animal`, `value` (None when no value can be given),
	`reason` (why not, or None), `stopped` (True when appreciation has stopped
	for this animal) and `basis` (band, matrix row, price, weight, date, age).
	"""
	doc = animal if hasattr(animal, "doctype") else frappe.get_doc("Animal", animal)
	s = s or settings()
	out = {"animal": doc.name, "value": None, "reason": None, "stopped": False, "basis": {}}

	w = latest_weight(doc.name)
	if not w:
		out["reason"] = _("No weight recorded.")
		return out
	weight, wdate, ref = w
	months = age_months(doc, on)
	band = band_of(doc, months)
	out["basis"] = {
		"band": band, "sex": doc.get("sex"), "age_months": months,
		"weight_kg": weight, "weight_date": str(wdate) if wdate else None, "weight_ref": ref,
	}
	row = matching_row(s.get(MATRIX) or [], band, doc.get("sex"), months, weight)
	if not row:
		out["reason"] = _("No priced matrix row fits a {0}.").format(band or _("animal"))
		return out

	out["basis"].update({"row": row.idx, "price_per_kg": flt(row.price_per_kg)})
	if cint(row.get("stop_after_months")) and months is not None and months >= cint(row.stop_after_months):
		out["stopped"] = True
		out["reason"] = _("Appreciation stops at {0} months.").format(row.stop_after_months)
		return out
	if cint(row.get("stop_at_first_calving")) and has_calved(doc):
		out["stopped"] = True
		out["reason"] = _("Appreciation stopped at first calving.")
		return out

	out["value"], out["basis"]["capped"] = value_for(row, weight)
	return out


# --------------------------------------------------------------------------- asset


def _asset_row(animal_name):
	link = frappe.db.get_value("Animal", animal_name, "asset_link")
	if not link:
		return None
	return frappe.db.get_value(
		"Asset", link,
		["name", "status", "docstatus", "disposal_date", "company", "cost_center", "calculate_depreciation"],
		as_dict=True,
	)


def asset_book_value(asset_name):
	from erpnext.assets.doctype.asset.asset import _get_asset_value_after_depreciation

	return flt(_get_asset_value_after_depreciation(asset_name))


def current_value(animal):
	"""The animal's value now. THE function other features should call.

	`value` is the asset's book value (after every adjustment and depreciation)
	when it has a live asset, else the matrix appraisal, else None. `source`
	says which. Both figures are returned so a caller can show the gap.
	"""
	name = animal.name if hasattr(animal, "doctype") else animal
	asset = _asset_row(name)
	book = None
	if asset and asset.docstatus == 1 and not asset.disposal_date and asset.status in LIVE_ASSET:
		book = asset_book_value(asset.name)
	appraisal = appraise(name)["value"]
	if book is not None:
		return {"animal": name, "value": book, "source": "asset", "asset": asset.name,
		        "asset_value": book, "appraised_value": appraisal}
	return {"animal": name, "value": appraisal, "source": "appraisal" if appraisal is not None else None,
	        "asset": asset.name if asset else None, "asset_value": None, "appraised_value": appraisal}


def _skip(animal, reason, **extra):
	return {"animal": animal, "status": "skipped", "reason": reason, **extra}


def _cost_center(asset, animal_doc):
	from upande_livestock.serverscripts.common import cost_center

	if asset.cost_center and cost_center.usable(asset.cost_center, asset.company):
		return asset.cost_center
	return cost_center.resolve(asset.company, animal_doc.get("current_herd"))


def _finance_book(asset_name, depreciates):
	if not depreciates:
		return None
	return frappe.db.get_value(
		"Asset Finance Book", {"parent": asset_name, "parenttype": "Asset", "finance_book": ["is", "set"]},
		"finance_book", order_by="idx",
	)


def already_posted(asset_name, ref):
	if not frappe.get_meta("Asset Value Adjustment").has_field("livestock_weight_ref"):
		return False
	return bool(frappe.db.exists(
		"Asset Value Adjustment", {"asset": asset_name, "docstatus": 1, "livestock_weight_ref": ref}
	))


def post_appreciation(animal, dry_run=1, s=None):
	"""Revalue one animal's asset from its latest weighing.

	Returns a dict with `status` of `posted`, `would_post` (dry run) or
	`skipped` and, always, `reason` when skipped. Never touches a disposed
	asset. Posts only when the new value differs from the asset's value by more
	than the minimum change, and falls only when decreases are allowed.
	"""
	dry = bool(cint(dry_run))
	s = s or settings()
	name = animal.name if hasattr(animal, "doctype") else animal
	doc = animal if hasattr(animal, "doctype") else frappe.get_doc("Animal", name)

	if doc.status not in LIVE_ANIMAL:
		return _skip(name, _("Animal is {0}.").format(doc.status))
	asset = _asset_row(name)
	if not asset:
		return _skip(name, _("No asset."))
	if asset.docstatus != 1 or asset.disposal_date or asset.status not in LIVE_ASSET:
		return _skip(name, _("Asset {0} is {1}.").format(asset.name, asset.status), asset=asset.name)

	a = appraise(doc, s=s)
	if a["value"] is None:
		return _skip(name, a["reason"], asset=asset.name, stopped=a["stopped"], basis=a["basis"])
	ref = a["basis"]["weight_ref"]
	if already_posted(asset.name, ref):
		return _skip(name, _("Weighing {0} is already posted.").format(ref), asset=asset.name, basis=a["basis"])

	current = asset_book_value(asset.name)
	target = flt(a["value"])
	diff = target - current
	minimum = flt(s.get("appreciation_min_change"))
	base = {"animal": name, "asset": asset.name, "current_value": current, "new_value": target,
	        "difference": diff, "basis": a["basis"]}
	if abs(diff) <= minimum or not diff:
		return {**base, "status": "skipped", "reason": _("Change of {0} is within the minimum of {1}.").format(
			f"{abs(diff):,.0f}", f"{minimum:,.0f}")}
	if diff < 0 and not cint(s.get("appreciation_allow_decrease")):
		return {**base, "status": "skipped", "reason": _("Value would fall and decreases are not allowed.")}

	if dry:
		return {**base, "status": "would_post"}
	if not is_enabled(s):
		return {**base, "status": "skipped", "reason": _("Appreciation is switched off in Livestock Settings.")}
	account = s.get("appreciation_account")
	if not account:
		return {**base, "status": "skipped", "reason": _("No Appreciation Account set in Livestock Settings.")}

	point = "appreciation"
	frappe.db.savepoint(point)
	try:
		ava = frappe.new_doc("Asset Value Adjustment")
		ava.company = asset.company
		ava.asset = asset.name
		ava.finance_book = _finance_book(asset.name, asset.calculate_depreciation)
		ava.date = today()
		ava.new_asset_value = target
		ava.difference_account = account
		ava.cost_center = _cost_center(asset, doc)
		ava.livestock_weight_ref = ref
		ava.livestock_basis = frappe.as_json(a["basis"], indent=None)
		ava.insert(ignore_permissions=True)
		ava.submit()
		frappe.db.release_savepoint(point)
	except Exception as e:
		frappe.db.rollback(save_point=point)
		frappe.log_error(title="Livestock appreciation error", message=frappe.get_traceback())
		return {**base, "status": "skipped", "reason": _("ERPNext refused the adjustment: {0}").format(str(e)[:200])}
	return {**base, "status": "posted", "adjustment": ava.name}


# --------------------------------------------------------------------------- bulk


def animals_with_assets():
	return frappe.get_all(
		"Animal",
		filters={"status": ["in", LIVE_ANIMAL], "asset_link": ["is", "set"]},
		pluck="name",
		order_by="name",
	)


def run(dry_run=0, s=None):
	"""Appreciate every live animal that has an asset. Returns a summary."""
	dry = bool(cint(dry_run))
	s = s or settings()
	rows, counts = [], {}
	up = down = 0.0
	for name in animals_with_assets():
		try:
			r = post_appreciation(name, dry_run=dry, s=s)
		except Exception:
			frappe.log_error(title="Livestock appreciation error", message=frappe.get_traceback())
			r = _skip(name, _("Unexpected error (see Error Log)."))
		rows.append(r)
		counts[r["status"]] = counts.get(r["status"], 0) + 1
		if r["status"] in ("posted", "would_post"):
			if r["difference"] > 0:
				up += r["difference"]
			else:
				down += r["difference"]
			if not dry and not frappe.flags.in_test:
				frappe.db.commit()  # keep what is done if a later animal dies
	reasons = {}
	for r in rows:
		if r["status"] == "skipped":
			reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
	if not dry:
		frappe.defaults.set_global_default(LAST_RUN_KEY, str(now_datetime()))
	return {
		"dry_run": int(dry), "animals": len(rows), "counts": counts,
		"total_increase": up, "total_decrease": down, "net": up + down,
		"skipped_reasons": reasons,
		"rows": [r for r in rows if r["status"] != "skipped"],
	}


# --------------------------------------------------------------------------- schedule


def slot_start(now, frequency, hour):
	"""The start of the current period's run slot: today / this Monday / the 1st, at `hour`."""
	d = getdate(now)
	if frequency == "Weekly":
		d = add_days(d, -((d.weekday() - WEEKLY_DAY) % 7))
	elif frequency == "Monthly":
		d = d.replace(day=1)
	return get_datetime(f"{d} {int(hour):02d}:00:00")


def is_due(now, frequency, hour, last_run):
	"""Whether the scheduled run should happen now.

	The run is due once `now` has passed this period's slot and nothing has run
	since the slot started, so an hour the scheduler missed is made up at the
	next tick. With no run on record it waits for the slot hour itself rather
	than firing the moment the switch is turned on.
	"""
	now = get_datetime(now)
	hour = min(max(cint(hour), 0), 23)
	slot = slot_start(now, frequency or "Weekly", hour)
	if now < slot:
		return False
	if last_run:
		return get_datetime(last_run) < slot
	return now.hour == hour and (frequency != "Weekly" or now.weekday() == WEEKLY_DAY) and (
		frequency != "Monthly" or now.day == 1
	)


def last_run():
	return frappe.defaults.get_global_default(LAST_RUN_KEY)


def run_if_due():
	"""Hourly scheduler entry point (hooks.scheduler_events)."""
	s = settings()
	if not is_enabled(s):
		return None
	if not is_due(now_datetime(), s.get("appreciation_frequency"), s.get("appreciation_hour"), last_run()):
		return None
	return run(dry_run=0)


# --------------------------------------------------------------------------- history

#: Who may post or run appreciation.
POSTING_ROLES = ("Livestock Manager", "Accounts Manager", "Accounts User", "System Manager")


def value_history(animal):
	"""Adjustments and posted depreciation of the animal's asset, newest first."""
	link = frappe.db.get_value("Animal", animal, "asset_link")
	if not link:
		return {"animal": animal, "asset": None, "events": []}
	asset = frappe.db.get_value(
		"Asset", link,
		["name", "status", "purchase_date", "net_purchase_amount", "value_after_depreciation", "docstatus"],
		as_dict=True,
	)
	events = []
	has_ref = frappe.get_meta("Asset Value Adjustment").has_field("livestock_weight_ref")
	fields = ["name", "date", "current_asset_value", "new_asset_value", "difference_amount",
	          "journal_entry", "docstatus"] + (["livestock_weight_ref", "livestock_basis"] if has_ref else [])
	for r in frappe.get_all("Asset Value Adjustment", filters={"asset": link, "docstatus": ["<", 2]}, fields=fields):
		events.append({
			"kind": "Adjustment", "date": str(r.date), "amount": flt(r.difference_amount),
			"value_after": flt(r.new_asset_value), "ref": r.name, "journal_entry": r.journal_entry,
			"basis": r.get("livestock_basis") or None, "weighing": r.get("livestock_weight_ref") or None,
		})
	for r in frappe.db.sql(
		"""select ds.schedule_date, ds.depreciation_amount, ds.journal_entry, ds.parent
		from `tabDepreciation Schedule` ds join `tabAsset Depreciation Schedule` p on p.name = ds.parent
		where p.asset = %s and p.docstatus = 1 and ifnull(ds.journal_entry, '') != ''""",
		link, as_dict=True,
	):
		events.append({
			"kind": "Depreciation", "date": str(r.schedule_date), "amount": -flt(r.depreciation_amount),
			"value_after": None, "ref": r.parent, "journal_entry": r.journal_entry, "basis": None, "weighing": None,
		})
	events.sort(key=lambda e: (e["date"], e["ref"]), reverse=True)
	return {
		"animal": animal, "asset": link, "status": asset.status if asset else None,
		"purchase_date": str(asset.purchase_date) if asset else None,
		"opening_value": flt(asset.net_purchase_amount) if asset else None,
		"current_value": flt(asset.value_after_depreciation) if asset else None,
		"events": events,
	}
