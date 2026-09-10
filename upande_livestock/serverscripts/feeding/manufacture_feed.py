"""Manufacture a herd's TMR through a Work Order.

Guards Work Order and Stock Entry because that is what it creates — asked
against the target DocType rather than a role, so renaming or re-scoping a role
cannot silently open it.

`portion` records a farm that feeds twice a day: 0.5 mixes and issues half the
day's ration. Nothing here enforces two halves — `feed_day_status` is what tells
the screen how much of the day is left, and a day that does not add up is a real
day, not an error.

`bom_no` lets a System run use a recipe the picker offers back (the herd's
standing ration, or a previously-used recipe made for it) instead of always
Herds.bom, without becoming a Manual run — the mislabel `manual_feed` was being
used to work around before this existed. Validated through `_base_for`, the
same check `manual_feed`'s `tuned_bom` uses to decide whether a `base_bom`
belongs to a herd, so both paths agree on what a herd may run and neither can
drift from the other. Omitted, this behaves exactly as before: the herd's own
standing ration."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard, run
from upande_livestock.serverscripts.feeding import _engine as feeding
from upande_livestock.serverscripts.feeding._tuned_bom import _base_for


@frappe.whitelist()
def manufacture_feed(
	herd, allow_shortage=False, employee=None, portion=1.0, posting_date=None, bom_no=None
):
	def go():
		guard("Work Order")
		guard("Stock Entry")
		resolved_bom_no = _base_for(herd, bom_no).name if bom_no else None
		res = feeding.manufacture_herd_feed(
			herd,
			allow_shortage=allow_shortage,
			employee=employee,
			portion=portion,
			posting_date=posting_date,
			bom_no=resolved_bom_no,
		)
		res["ok"] = True
		return res

	return run(go, "livestock manufacture_feed failed")
