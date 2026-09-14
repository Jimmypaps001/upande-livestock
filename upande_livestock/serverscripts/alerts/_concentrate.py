# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Is there enough concentrate to keep feeding, and for how much longer?

The one alert on this farm that is not about an animal. A cow that is overdue
for a move is still fed tomorrow; a concentrate that runs out stops eight herds
at once, and it stops them on a morning nobody chose.

COVER IS COUNTED IN DAYS, NOT IN KILOGRAMS. "412 kg of calves meal" means
nothing without the herd behind it — 412 kg is six weeks for the calves and two
days for the milkers. `concentrate_plan` already does that arithmetic off the
head counts and the rations, so this reads days of cover and says so in days.

TWO KINDS, BECAUSE THEY NEED DIFFERENT ANSWERS:

  Concentrate Low   the bin will be empty in fewer days than the farm asked to
                    be warned about. The answer is to mix a batch.
  Concentrate Out   there is nothing left, OR a batch cannot be mixed because
                    the raw materials for it are short. The answer is to buy
                    something, and no amount of mixing will help.

The second is not a louder version of the first. A farm told "low" when the
truth is "you cannot fix this by mixing" mixes, fails, and finds out a day
later.
"""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.timings import ALL_TIMING_DEFAULTS, read_setting
from upande_livestock.serverscripts.feeding.concentrate_plan import concentrate_plan

COVER_FIELD = "custom_concentrate_cover_days"


def cover_days():
	"""Days of cover below which the farm wants to be told. 0 disables it."""
	stored = read_setting(COVER_FIELD)
	if stored is None:
		return flt(ALL_TIMING_DEFAULTS[COVER_FIELD])
	return flt(stored)


def _phrase(days):
	if days is None:
		return "nothing is eating it"
	if days < 1:
		return "less than a day left"
	if days < 2:
		return "about a day left"
	return f"about {int(days)} days left"


def concentrate_alerts():
	"""Everything worth saying about the concentrate store. Writes nothing."""
	limit = cover_days()
	if limit <= 0:
		return []

	plan = concentrate_plan(1)
	if not plan.get("ok"):
		return []

	out = []
	for row in plan["concentrates"]:
		per_day = flt(row.get("per_day_kg"))
		if per_day <= 0:
			# Nothing is eating it, so there is no such thing as running out.
			continue
		on_hand = flt(row.get("on_hand_kg"))
		days = flt(row.get("days_cover")) if row.get("days_cover") is not None else None
		short = row.get("short") or []
		name = row.get("item_name") or row["item_code"]

		if on_hand <= 0 or not row.get("can_mix"):
			out.append({
				"kind": "Concentrate Out",
				"item": row["item_code"],
				"label": name,
				"severity": "Overdue",
				"message": _out_message(name, on_hand, short),
				"detail": {"on_hand_kg": on_hand, "per_day_kg": per_day,
				           "days_cover": days, "short": short},
			})
		elif days is not None and days < limit:
			out.append({
				"kind": "Concentrate Low",
				"item": row["item_code"],
				"label": name,
				"severity": "Due",
				"message": (
					f"{name} is down to {round(on_hand)} kg — {_phrase(days)} at "
					f"{round(per_day)} kg a day. Mix a batch before it runs out."
				),
				"detail": {"on_hand_kg": on_hand, "per_day_kg": per_day,
				           "days_cover": days, "to_mix_kg": flt(row.get("to_mix_kg"))},
			})
	return out


def _out_message(name, on_hand, short):
	"""Say which raw material is missing, not just that mixing failed.

	"Cannot mix" sends someone to the store to find out why. Naming the item
	sends them to the supplier, which is the only thing that fixes it.
	"""
	if short:
		missing = ", ".join(
			frappe.db.get_value("Item", s.get("item_code"), "item_name") or s.get("item_code")
			for s in short[:3]
		)
		more = f" and {len(short) - 3} more" if len(short) > 3 else ""
		return (
			f"{name} cannot be mixed — the store is short of {missing}{more}. "
			f"Mixing will not fix this; it has to be bought."
		)
	return f"{name} has run out. Mix a batch before the next feed."
