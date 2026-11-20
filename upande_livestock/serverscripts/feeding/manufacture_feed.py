"""Manufacture a herd's TMR through a Work Order.

Guards Work Order and Stock Entry because that is what it creates — asked
against the target DocType rather than a role, so renaming or re-scoping a role
cannot silently open it.

`feed_session` says whether this is a Full day or a Half day ("Half" is the next
half: session 1 of 2, then 2 of 2). A half mixes and issues exactly half of the
ration and is kept as a Livestock Feed Session (`_sessions`), which tells
`feed_day_status` and the screens what is fed and what is owed. Feeding more
than a day (a third session, a Full after a half) is refused unless `override`
is set by a Livestock Manager or System Manager. `portion` still works for a
caller that has no session: 0.5 is read as a half, 1 as a full day.

`bom_no` lets a System run use a recipe the picker offers back (the herd's
standing ration, or a previously-used recipe made for it) instead of always
Herds.bom, without becoming a Manual run — the mislabel `manual_feed` was being
used to work around before this existed. Validated through `_base_for`, the
same check `manual_feed`'s `tuned_bom` uses to decide whether a `base_bom`
belongs to a herd, so both paths agree on what a herd may run and neither can
drift from the other. Omitted, this behaves exactly as before: the herd's own
standing ration.

`source_warehouse` names the store the ingredients come out of and the batch is
issued from. Omitted, every configured feed store is searched in order, which is
what this always did.

`source_by_item` and `batch_by_item` are finer than that, and are what the
Feeding page actually sends: a store and a batch per INGREDIENT, because a TMR
draws its silage from a pit and its concentrate from the mixing store, and one
dropdown for all four lines is a run nobody can post as the farm works."""

import frappe
from frappe.utils import flt, today

from upande_livestock.serverscripts.common import event_types
from upande_livestock.serverscripts.common.envelope import guard_stock, run
from upande_livestock.serverscripts.feeding import _engine as feeding
from upande_livestock.serverscripts.feeding import _feed_types as feed_types
from upande_livestock.serverscripts.feeding import _sessions as sessions
from upande_livestock.serverscripts.feeding._tuned_bom import _base_for


@frappe.whitelist()
def manufacture_feed(
	herd, allow_shortage=False, employee=None, portion=1.0, posting_date=None, bom_no=None,
	source_warehouse=None, source_by_item=None, batch_by_item=None,
	feed_session=None, override=False,
):
	def go():
		# A farm that switched Feeding off (Settings → Events) is refused in
		# words before any stock moves — not left to the Feeding event failing
		# after the feed has already left the store.
		event_types.assert_enabled("Feeding")
		feed_types.assert_on(feed_types.SYSTEM)
		guard_stock("Work Order", "Stock Entry")
		resolved_bom_no = _base_for(herd, bom_no).name if bom_no else None
		# Full day or half day: the session decides the share of the day mixed. A
		# caller that sends only a portion (older phones) is read as a half when it
		# is 0.5, and as a whole day when it is 1.
		day = posting_date or today()
		odd = not feed_session and flt(portion) not in (0.0, 1.0, 0.5)
		if odd:
			# A share that is neither a whole nor a half day: honoured as sent, outside the session rules.
			name, fraction, overridden = "Full", flt(portion), False
		else:
			choice = feed_session or ("Half" if flt(portion) == 0.5 else None)
			name, fraction, overridden = sessions.resolve(herd, day, choice, override)
		res = feeding.manufacture_herd_feed(
			herd,
			allow_shortage=allow_shortage,
			employee=employee,
			portion=fraction,
			posting_date=posting_date,
			bom_no=resolved_bom_no,
			source_warehouse=source_warehouse,
			source_by_item=frappe.parse_json(source_by_item) if source_by_item else None,
			batch_by_item=frappe.parse_json(batch_by_item) if batch_by_item else None,
		)
		_record_session(herd, day, name, fraction, overridden, res, resolved_bom_no)
		res["ok"] = True
		return res

	return run(go, "livestock manufacture_feed failed")


def _record_session(herd, day, name, fraction, overridden, res, bom_no):
	"""Keep the System run as a session of the herd's day and report the day's state."""
	heads = res.get("heads") or 0
	bom = frappe.get_doc("BOM", res.get("bom_no") or bom_no or frappe.db.get_value("Herds", herd, "bom"))
	comps = [
		{
			"item_code": r.item_code, "item_name": r.item_name or r.item_code, "uom": r.uom or r.stock_uom or "",
			"planned_kg": flt(r.qty) * heads * fraction, "fed_kg": flt(r.qty) * heads * fraction,
		}
		for r in bom.items
	]
	standing = frappe.db.get_value("Herds", herd, "bom")
	total = flt(res.get("produced_qty"))
	sessions.record(
		herd, day, name, fraction, "System", res, heads=heads, components=comps, planned_kg=total, fed_kg=total,
		amended=bool(bom_no and standing and bom_no != standing), overridden=overridden,
	)
	res["session"] = sessions.session_state(herd, day)
