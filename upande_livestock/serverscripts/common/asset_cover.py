# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Insurance cover of an animal, read from and written through Upande Asset.

An animal that is capitalised is an ERPNext Asset (`Animal.asset_link`), and
Upande Asset's Insurance Policy is where an Asset is put under cover. Nothing is
reimplemented here:

* READING asks Upande Asset's own `get_covering_rows` which policy rows cover
  the Asset today, and falls back to the insurance fields Upande Asset itself
  keeps on the Asset (insurance_end_date ...) to tell "expired" from "none".
* PUTTING UNDER COVER calls Upande Asset's whitelisted
  `insurance_policy.endorse` with the "Add Assets" action, so its role check,
  pro-rata premium, ToDo for the insurer and policy rules all apply. Without an
  insurer endorsement number that is a request waiting for the insurer; with
  one it is confirmed at once.

When Upande Asset (or its insurance module) is not on the site, every read
answers state "unavailable" instead of failing, so the animal pages still draw.

States: insured, expiring, expired, none, no_asset, unavailable.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

ENDORSE = "upande_asset.upande_asset.doctype.insurance_policy.insurance_policy.endorse"
NATIVE = ("insurance_policy", "policy_number", "insurer", "insured_value",
          "insurance_start_date", "insurance_end_date")
LIVE = ("Active", "Expiring", "Renewal In Progress", "Awaiting Premium")
EXPIRING_DAYS = 30


def available():
	"""True when Upande Asset's insurance module is installed on this site."""
	try:
		from upande_asset.upande_asset.insurance import utils  # noqa: F401
	except Exception:
		return False
	return bool(frappe.db.exists("DocType", "Insurance Policy"))


def _empty(state):
	return {"state": state, "policy": None, "policyNumber": None, "insurer": None,
	        "sumInsured": None, "start": None, "end": None, "daysLeft": None}


def _state_for(end, start=None, threshold=EXPIRING_DAYS):
	if not end:
		return "none"
	left = date_diff(getdate(end), getdate(today()))
	if left < 0:
		return "expired"
	if start and getdate(start) > getdate(today()):
		return "none"
	return "expiring" if left <= threshold else "insured"


def cover_for_asset(asset):
	"""Cover summary of one Asset (authoritative: asks the policies)."""
	if not asset:
		return _empty("no_asset")
	if not available():
		return _empty("unavailable")
	try:
		from upande_asset.upande_asset.insurance.utils import get_covering_rows, get_expiring_threshold

		rows = [r for r in get_covering_rows(asset) if r.status != "Cancelled" and r.row_status != "Removed"]
		threshold = get_expiring_threshold()
		if rows:
			r = max(rows, key=lambda x: getdate(x.end_date))
			return {
				"state": _state_for(r.end_date, threshold=threshold),
				"policy": r.policy,
				"policyNumber": r.policy_number,
				"insurer": r.insurer_name or r.insurer,
				"sumInsured": flt(r.sum_insured),
				"start": str(r.start_date),
				"end": str(r.end_date),
				"daysLeft": date_diff(getdate(r.end_date), getdate(today())),
			}
	except Exception:
		frappe.log_error(title="livestock asset cover failed")
		return _empty("unavailable")
	return _from_native(frappe.db.get_value("Asset", asset, list(_native_fields()), as_dict=True))


def _native_fields():
	meta = frappe.get_meta("Asset")
	return [f for f in NATIVE if meta.has_field(f)]


def _from_native(v):
	v = v or {}
	end = v.get("insurance_end_date")
	if not end:
		return _empty("none")
	out = _empty("expired" if getdate(end) < getdate(today()) else "none")
	out.update({
		"policy": v.get("insurance_policy"),
		"policyNumber": v.get("policy_number"),
		"insurer": v.get("insurer"),
		"sumInsured": flt(v.get("insured_value")) or None,
		"start": str(v["insurance_start_date"]) if v.get("insurance_start_date") else None,
		"end": str(end),
		"daysLeft": date_diff(getdate(end), getdate(today())),
	})
	return out


def covers_for_animals(animals):
	"""{animal: state} for a list — one query, from the Asset's own insurance fields.

	Cheap enough for the search list; the profile asks the policies themselves.
	"""
	animals = list(animals)
	if not animals:
		return {}
	if not available():
		return {a: "unavailable" for a in animals}
	links = dict(frappe.get_all("Animal", filters={"name": ["in", animals]},
	                            fields=["name", "asset_link"], as_list=True))
	assets = [v for v in links.values() if v]
	native = {}
	fields = _native_fields()
	if assets and "insurance_end_date" in fields:
		for r in frappe.get_all("Asset", filters={"name": ["in", assets]},
		                        fields=["name", "insurance_start_date", "insurance_end_date"]):
			native[r.name] = _state_for(r.insurance_end_date, r.insurance_start_date)
	return {a: ("no_asset" if not links.get(a) else native.get(links[a], "none")) for a in animals}


def cover_for_animal(animal):
	asset = frappe.db.get_value("Animal", animal, "asset_link")
	out = cover_for_asset(asset)
	out["asset"] = asset
	return out


def open_policies(company=None):
	"""Submitted policies whose cover is running, for the picker."""
	if not available():
		return []
	filters = {"docstatus": 1, "status": ["in", LIVE], "insurance_for": "Assets",
	           "end_date": [">=", today()]}
	if company:
		filters["company"] = company
	return frappe.get_all("Insurance Policy", filters=filters,
	                      fields=["name", "policy_number", "policy_type", "insurer_name",
	                              "start_date", "end_date", "company"], order_by="end_date desc")


def put_under_cover(animal, policy, sum_insured=None, effective_date=None, endorsement_no=None):
	"""Add the animal's Asset to an Upande Asset policy. Returns Upande Asset's answer.

	Raises with a plain message when the animal has no Asset, Upande Asset is not
	installed, or the policy refuses (Upande Asset only lets an Accounts Manager
	endorse; that refusal is passed on as it is).
	"""
	if not available():
		frappe.throw(_("Upande Asset's insurance is not installed on this site."))
	asset = frappe.db.get_value("Animal", animal, "asset_link")
	if not asset:
		frappe.throw(_("{0} is not on the fixed-asset register, so she cannot be insured.").format(animal))
	if not policy:
		frappe.throw(_("Choose the policy."))
	if cover_for_asset(asset)["state"] in ("insured", "expiring"):
		frappe.throw(_("{0} is already under cover.").format(animal))
	value = flt(sum_insured) or flt(frappe.db.get_value("Asset", asset, "value_after_depreciation"))
	start, end = frappe.db.get_value("Insurance Policy", policy, ["start_date", "end_date"])
	eff = getdate(effective_date or today())
	eff = min(max(eff, getdate(start)), getdate(end))
	payload = {"effective_date": str(eff), "assets": [{"asset": asset, "sum_insured": value}]}
	if endorsement_no:
		payload["endorsement_no"] = endorsement_no
	# Upande Asset only lets a policy carry an Asset flagged Insurance Required.
	if frappe.get_meta("Asset").has_field("insurance_required") and not frappe.db.get_value(
			"Asset", asset, "insurance_required"):
		frappe.db.set_value("Asset", asset, "insurance_required", 1)
	try:
		res = frappe.call(ENDORSE, policy=policy, action="Add Assets", payload=payload)
	except frappe.PermissionError:
		frappe.throw(_("Upande Asset only lets an Accounts Manager endorse a policy. Ask one to insure {0}.").format(animal))
	res = dict(res or {})
	res["asset"] = asset
	return res
