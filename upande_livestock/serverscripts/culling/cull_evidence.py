# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The case for culling one animal, in figures."""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES, service_record
from upande_livestock.serverscripts.common.envelope import guard_read, run


def _median(values):
	rows = sorted(v for v in values if v is not None)
	if not rows:
		return None
	mid = len(rows) // 2
	return rows[mid] if len(rows) % 2 else (rows[mid - 1] + rows[mid]) / 2.0


@frappe.whitelist()
def cull_evidence(animal=None):
	"""Her figures beside the herd's, and a sentence saying what they amount to.

	MEDIAN, NOT MEAN, and taken over the animals that have each measure. One
	nine-lactation matriarch drags a mean far enough that half the herd reads
	as below average, which is exactly the comparison this exists to make
	honest; and a maiden heifer counted as a zero calving interval would make
	every cow that has calved look good.

	It never returns a verdict. A productive cow may still be culled — she may
	be lame, or bad-tempered, or the farm may simply need the space — so this
	says what is true and leaves the decision to a person. `was_productive` is
	there to be written on the record, not to block anything.
	"""

	def go():
		guard_read("Animal")
		if not animal:
			frappe.throw(frappe._("Select the animal."))

		her = frappe.db.get_value(
			"Animal", animal,
			["name", "burn_name", "current_herd", "sex", "date_of_birth", "status",
			 "parity", "last_calving_date", "is_capitalised", "asset_link"],
			as_dict=True,
		)
		if not her:
			frappe.throw(frappe._("{0} is not an animal on this farm.").format(animal))

		herd = frappe.get_all(
			"Animal",
			filters=[["status", "not in", list(RETIRED_STATUSES)], ["disabled", "=", 0],
			         ["sex", "=", "Female"]],
			fields=["name", "parity"], limit_page_length=0,
		)
		record = service_record([r.name for r in herd] + [her.name])
		med_parity = _median([flt(r.parity) for r in herd if flt(r.parity) > 0])
		med_rate = _median(
			[record[r.name]["conception_rate"] for r in herd if r.name in record]
		)
		her_rate = (record.get(her.name) or {}).get("conception_rate")

		measures = []
		below = 0
		for label, mine, theirs, unit in (
			("Calvings", flt(her.parity), med_parity, ""),
			("Conception rate", her_rate, med_rate, "%"),
		):
			if mine is None or theirs is None:
				continue
			is_below = mine < theirs
			below += 1 if is_below else 0
			measures.append({
				"label": label, "hers": mine, "herd": theirs,
				"unit": unit, "below": is_below,
			})

		measured = len(measures)
		was_productive = measured > 0 and below == 0
		if not measured:
			case = "There are no figures on her yet to compare."
		elif below == 0:
			case = "She is at or above the herd on every measure there is."
		elif below == measured:
			case = "She is below the herd on every measure there is."
		else:
			case = f"She is below the herd on {below} of {measured} measures."

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
			"was_productive": was_productive,
			"case": case,
			"book_value": _book_value(her.asset_link),
			"is_capitalised": bool(her.is_capitalised),
			"asset": her.asset_link,
			"policy": claim,
		}

	return run(go, "livestock cull_evidence failed")


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
