# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The case for culling one animal, in figures."""

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, today

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.gain import adg_between, herd_target_adg, weights_for
from upande_livestock.serverscripts.common.gain import period_days as _period


@frappe.whitelist()
def cull_evidence(animal=None, period_days=None):
	"""Its gain beside its herd's target, its health history, and a sentence
	saying what they amount to.

	It never returns a verdict. A fast-growing bull may still be culled — it
	may be lame, or vicious, or the farm may simply need the space — so this
	says what is true and leaves the decision to a person.
	"""

	def go():
		guard_read("Animal")
		if not animal:
			frappe.throw(frappe._("Select the animal."))

		her = frappe.db.get_value(
			"Animal", animal,
			["name", "burn_name", "current_herd", "sex", "date_of_birth", "status",
			 "is_capitalised", "asset_link"],
			as_dict=True,
		)
		if not her:
			frappe.throw(frappe._("{0} is not an animal on this farm.").format(animal))

		days = _period(period_days)
		adg = adg_between(weights_for(animal), add_days(today(), -days), today())
		target = herd_target_adg(her.current_herd)
		sick_days, cases = _health_history(animal)

		measures = []
		below = 0
		if adg is not None and target:
			is_below = adg < target
			below += 1 if is_below else 0
			measures.append({
				"label": f"Daily gain ({days} days)", "hers": round(adg, 3),
				"herd": round(target, 3), "unit": "kg/d", "below": is_below,
			})
		measured = len(measures)

		if not measured:
			case = "There are not enough weighings, or no gain target, to compare its gain."
		elif below:
			case = f"It is gaining {adg:.2f} kg/day against a target of {target:.2f}."
		else:
			case = f"It is gaining {adg:.2f} kg/day, at or above the target of {target:.2f}."
		if cases:
			case += f" {int(sick_days)} days ill over {cases} health case{'' if cases == 1 else 's'} in the last year."

		claim = _open_policy(animal)
		return {
			"ok": True,
			"animal": her.name,
			"name": her.burn_name or her.name,
			"herd": her.current_herd,
			"status": her.status,
			"measures": measures,
			"below": below,
			"measured": measured,
			"period_adg": None if adg is None else round(adg, 3),
			"target_adg": None if not target else round(target, 3),
			"sick_days": sick_days,
			"health_cases": cases,
			"case": case,
			"book_value": _book_value(her.asset_link),
			"is_capitalised": bool(her.is_capitalised),
			"asset": her.asset_link,
			"policy": claim,
		}

	return run(go, "livestock cull_evidence failed")


def _health_history(animal):
	"""Days under treatment, and the number of cases, over the last year."""
	year_ago = getdate(add_days(today(), -365))
	days, cases = 0.0, 0
	for row in frappe.db.sql(
		"""SELECT opened_date, closed_date, duration_days FROM `tabLivestock Health Case`
		   WHERE docstatus = 1 AND animal = %s AND opened_date >= %s""",
		(animal, year_ago), as_dict=True,
	):
		cases += 1
		if row.duration_days:
			days += flt(row.duration_days)
		else:
			end = getdate(row.closed_date) if row.closed_date else getdate(today())
			days += max(date_diff(end, getdate(row.opened_date)), 0)
	return days, cases


def _book_value(asset):
	"""What her Asset is worth today, depreciation included.

	Read off the Asset because Animal's own `current_book_value` was written
	once, at purchase, and never depreciated — and was 0 on every animal the
	asset migration carried over. Not capitalised means nothing on the books.
	"""
	if not asset:
		return 0.0
	from erpnext.assets.doctype.asset.asset import get_asset_value_after_depreciation

	return flt(get_asset_value_after_depreciation(asset))


def _open_policy(animal):
	"""A policy covering her today, if there is one.

	Read at the moment of raising rather than at the moment of death, so the
	person proposing knows there is a claim to make before they choose a flow.
	By its dates, the way the claim itself is judged: nothing ever marks a
	policy Expired, so `status = Active` alone showed lapsed cover as live.
	"""
	from upande_livestock.serverscripts.culling.raise_insurance_claim import covering_policy

	return covering_policy(animal, None)
