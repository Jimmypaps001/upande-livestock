# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Bull Performance: the animals of one herd ranked by average daily gain.

Three gains are reported per animal. *Period* ADG (over a window, 90 days by
default) is the ranking figure; *herd* ADG runs from its first weighing in this
herd; *lifetime* ADG from birth weight, or its first weighing. An animal with
fewer than two weighings in the period has no period ADG (None, never 0), is
not ranked and is listed last.
"""

import frappe
from frappe.utils import add_days, date_diff, getdate, today

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES, live_herd_count
from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.common.gain import (
	DEFAULT_PERIOD_DAYS,
	adg_between,
	herd_target_adg,
	period_days as _period,
	weights_for_many,
)

PERFORMANCE_CLASSES = ("Fattening", "Breeding", "Calf")


def _round(value, places=3):
	return None if value is None else round(value, places)


def herd_rows(herd, animals, period_days):
	"""Per-animal rows, unsorted and unranked."""
	names = [a.name for a in animals]
	weighings = weights_for_many(names, birth=False)
	lifetime = weights_for_many(names)
	in_herd = weights_for_many(names, herd=herd)
	end = getdate(today())
	start = add_days(end, -period_days)
	rows = []
	for a in animals:
		latest = weighings[a.name][-1] if weighings[a.name] else None
		rows.append({
			"animal": a.name,
			"label": a.burn_name or a.name,
			"latest_weight_kg": latest[1] if latest else None,
			"latest_weight_date": str(latest[0]) if latest else None,
			"days_since_weighing": date_diff(end, latest[0]) if latest else None,
			"period_adg": _round(adg_between(weighings[a.name], start, end)),
			"herd_adg": _round(adg_between(in_herd[a.name])),
			"lifetime_adg": _round(adg_between(lifetime[a.name])),
			"rank": None,
			"below_target": None,
		})
	return rows


def active_animals(herd):
	"""The herd's live animals — in a Breeding herd (a mating group) the bulls only:
	the cows running with them are not ranked as bulls."""
	filters = {"current_herd": herd, "docstatus": ["!=", 2], "disabled": 0, "status": ["not in", RETIRED_STATUSES]}
	if frappe.db.get_value("Herds", herd, "herd_class") == "Breeding":
		filters["sex"] = "Male"
	return frappe.get_all(
		"Animal",
		filters=filters,
		fields=["name", "burn_name", "date_of_birth", "birth_weight_kg"],
	)


@frappe.whitelist()
def get_bull_performance(herd: str, period_days: int = DEFAULT_PERIOD_DAYS) -> dict:
	guard_read("Animal")
	days = _period(period_days)
	herd_class, target_adg = None, None
	if frappe.db.exists("Herds", herd):
		herd_class = frappe.db.get_value("Herds", herd, "herd_class")
		target_adg = herd_target_adg(herd)

	rows = herd_rows(herd, active_animals(herd), days)

	ranked = sorted((r for r in rows if r["period_adg"] is not None), key=lambda r: -r["period_adg"])
	previous, previous_rank = None, 0
	for i, r in enumerate(ranked, start=1):
		if r["period_adg"] != previous:
			previous, previous_rank = r["period_adg"], i
		r["rank"] = previous_rank
		r["below_target"] = None if target_adg is None else r["period_adg"] < target_adg
	unranked = sorted((r for r in rows if r["period_adg"] is None), key=lambda r: r["label"])

	weights = [r["latest_weight_kg"] for r in rows if r["latest_weight_kg"] is not None]
	gains = [r["period_adg"] for r in ranked]
	return {
		"herd": herd,
		"herd_class": herd_class,
		"target_adg_kg": target_adg,
		"period_days": days,
		"summary": {
			"head_count": len(rows),
			"avg_weight_kg": _round(sum(weights) / len(weights), 1) if weights else None,
			"avg_period_adg": _round(sum(gains) / len(gains)) if gains else None,
		},
		"rows": ranked + unranked,
	}


@frappe.whitelist()
def list_performance_herds() -> list:
	guard_read("Animal")
	herds = frappe.get_all(
		"Herds",
		filters={"herd_class": ["in", PERFORMANCE_CLASSES]},
		fields=["name", "herd_class"],
		order_by="herd_class asc, name asc",
	)
	return [{"herd": h.name, "herd_class": h.herd_class, "head_count": len(active_animals(h.name))
	         if h.herd_class == "Breeding" else live_herd_count(h.name)} for h in herds]
