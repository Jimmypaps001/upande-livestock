# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""How one animal stands against the others on the farm.

Two comparisons, both over the animals that HAVE the measure: her herd, and her
group — the breeding cows if she is one, otherwise the animals at the same stage
(heifers with heifers). A heifer measured against the breeding cows would read as
"bottom of the farm" on every figure she cannot have yet.

Every measure is read for every live animal in a handful of grouped queries (the
animals, their stage facts, their service counts, their calving dates), then
compared in memory — never one query per animal.

`top` is her rank among those compared, as a share: 10 means the best tenth. It
is None for the measures with no better end (weight, parity), which
are shown against the average and not ranked. Ties share the better rank.
"""

import frappe
from frappe.utils import date_diff, flt, getdate

from upande_livestock.serverscripts.common import animal_stage
from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES, service_record
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run

BREEDING_STAGES = ("fresh", "open", "served", "confirmed")

#: key, label, unit, which end is better (None: neither).
MEASURES = (
	("parity", "Parity", "", None),
	("services_per_conception", "Services per conception", "", "lower"),
	("calving_interval", "Calving interval", "d", "lower"),
	("last_weight", "Last weight", "kg", None),
)


def _group_of(stage, has_calving):
	if stage in BREEDING_STAGES and has_calving:
		return "breeding", "the breeding cows"
	return stage, f"{stage} animals"


def _calving_intervals(names):
	"""{animal: mean days between her calvings}, from one grouped query.

	(last - first) / (distinct calving dates - 1) is exactly the mean of the gaps,
	and counting distinct DATES keeps twins from reading as a zero-day interval.
	"""
	if not names:
		return {}
	rows = frappe.db.sql(
		"""select animal, count(distinct event_date) n, min(event_date) first, max(event_date) last
		from `tabLivestock Event`
		where docstatus = 1 and event_type = 'Calving' and animal in %(names)s
		group by animal having n >= 2""",
		{"names": tuple(names)},
		as_dict=True,
	)
	return {r.animal: date_diff(getdate(r.last), getdate(r.first)) / (r.n - 1) for r in rows}


def _standing(value, peers, better):
	"""Her figure against `peers` (values, her own among them)."""
	peers = [p for p in peers if p is not None]
	if not peers or value is None:
		return {"avg": None, "n": len(peers), "top": None}
	out = {"avg": round(sum(peers) / len(peers), 1), "n": len(peers), "top": None}
	if better:
		ahead = sum(1 for p in peers if (p < value if better == "lower" else p > value))
		out["top"] = max(1, round(100.0 * (ahead + 1) / len(peers)))
	return out


@frappe.whitelist()
def animal_standing(payload=None):
	"""One animal's measures, with her herd's and her group's average and rank."""

	def go():
		guard_read("Animal")
		name = (as_dict(payload).get("animal") or "").strip()
		if not name:
			frappe.throw(frappe._("Select an animal."))

		rows = frappe.get_all(
			"Animal",
			filters=[["status", "not in", list(RETIRED_STATUSES)], ["disabled", "=", 0]],
			fields=["name", "current_herd", "date_of_birth", "status", "disabled", "parity", "last_weight_kg"],
			limit_page_length=0,
		)
		by_name = {r.name: r for r in rows}
		if name not in by_name:
			frappe.throw(frappe._("{0} is not a live animal on this farm.").format(name))

		names = list(by_name)
		facts = animal_stage.facts_for(names)
		record = service_record(names)
		intervals = _calving_intervals(names)
		today_ = frappe.utils.today()

		figures, groups = {}, {}
		for r in rows:
			f = facts[r.name]
			cyc = animal_stage.cycle(r, f)
			g = _group_of(cyc["stage"], bool(f["calving"]))
			groups[r.name] = g
			s = record.get(r.name)
			figures[r.name] = {
				"parity": flt(r.parity) or None,
				# Only a cow with a confirmed conception has a ratio; one that has
				# been served and not yet held has none, not an infinite one.
				"services_per_conception": round(s["services"] / s["held"], 1) if s and s["held"] else None,
				"calving_interval": round(intervals[r.name]) if r.name in intervals else None,
				"last_weight": flt(r.last_weight_kg) or None,
			}

		mine = by_name[name]
		group_key, group_label = groups[name]
		herd_names = [n for n, r in by_name.items() if r.current_herd == mine.current_herd]
		group_names = [n for n in names if groups[n][0] == group_key]

		metrics = []
		for key, label, unit, better in MEASURES:
			value = figures[name][key]
			metrics.append({
				"key": key, "label": label, "unit": unit, "better": better, "value": value,
				"herd": _standing(value, [figures[n][key] for n in herd_names], better),
				"group": _standing(value, [figures[n][key] for n in group_names], better),
			})

		return {
			"ok": True,
			"asOf": today_,
			"animal": name,
			"herd": {"name": mine.current_herd or "no herd", "n": len(herd_names)},
			"group": {"key": group_key, "label": group_label, "n": len(group_names)},
			"metrics": metrics,
		}

	return run(go, "livestock animal_standing failed")
