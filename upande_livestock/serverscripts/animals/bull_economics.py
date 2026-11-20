# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What a bull has cost the farm against what he is worth.

Kaitet sells bulls as soon as they are born: there is no natural service, so a
bull that stays is feed with nothing coming back. This puts a number on that.

COST METHOD (stated, because it is an allocation, not a measurement). The farm
feeds a pen, never an animal. One Livestock Feed Actual holds a herd's day: what
went into the mixer, per component. A bull is charged, for each day he stood in
a herd, that herd's feed cost for the day divided by the head fed that day
(`head_count` on the record) -- the same equal-share rule `feed_actuals.
per_animal_intake` uses for kilograms. Each kilogram line is priced at the
item's average Bin valuation rate (stock held, else Item valuation rate, else
last purchase rate), converted from kilograms to the item's stock unit where
they differ. Which herd he stood in on a day comes from his Movement events
(the same spells the profile draws). Days with no feed record cost nothing: the
figure is what was recorded, not an estimate of what was not.

VALUE. His Asset's value_after_depreciation (gross purchase amount if that is
blank); with no Asset, Livestock Settings "Bull Price per kg" x his last
weight; with neither, no value, and the net is null rather than a made-up 0.

BURDEN SINCE is the first day the running feed cost passes his value. It is
measured against today's value, which is an approximation (an Asset depreciates
and a bull grows); it says "from about this day", not "to the shilling".

PURPOSE. "Cull for sale at birth" means every day he is kept is cost, so the
answer also carries `kept_as_cost` and `days_kept`.

Read-guarded on Animal.
"""

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.feeding._units import is_kg

PURPOSES = ("Cull for sale at birth", "Fattening", "Breeding")
DEFAULT_PURPOSE = "Cull for sale at birth"
RETIRED = ("Dead", "Deceased", "Sold", "Culled", "Disposed", "Transferred Out")
METHOD = "Herd feed cost for each day he stood in the herd, divided by the head fed that day."


def purpose():
	"""The farm's bull purpose, the Kaitet default when none is stored."""
	value = frappe.db.get_single_value("Livestock Settings", "bull_purpose")
	return value if value in PURPOSES else DEFAULT_PURPOSE


# ---------------------------------------------------------------------------
# pure arithmetic -- no database, so it is testable on its own
# ---------------------------------------------------------------------------


def accumulate(daily, value):
	"""(total, burden_since) from [(date, cost)] in any order, against `value`.

	`burden_since` is the first date the running total is above `value`; None
	when it never is, or when there is no value to compare with.
	"""
	total, since = 0.0, None
	for day, cost in sorted(daily, key=lambda p: str(p[0])):
		total += flt(cost)
		if since is None and value is not None and total > flt(value):
			since = str(day)
	return flt(total, 2), since


def net_of(value, cost):
	"""value - cost, or None when there is no value to subtract from."""
	return None if value is None else flt(flt(value) - flt(cost), 2)


def days_in(spells, costs, start, end):
	"""[(date, cost)] for the days he stood in each spell's herd.

	`spells` are {herd, from, to} (`to` None = still there), `costs` is
	{herd: {date: per-head cost}}. A day belongs to the spell it starts in, so
	the day he moves is counted once, in the herd he moved to.
	"""
	out = []
	for s in spells:
		lo = max(str(s["from"]), str(start))
		hi = min(str(s["to"]) if s.get("to") else str(add_days(end, 1)), str(add_days(end, 1)))
		for day, cost in (costs.get(s["herd"]) or {}).items():
			if lo <= str(day) < hi:
				out.append((str(day), cost))
	return out


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------


class _Cache:
	"""Item rates and each herd's per-head feed cost by day, read once per call."""

	def __init__(self):
		self.rates = {}
		self.herds = {}

	def rate_per_stock_unit(self, code):
		if code not in self.rates:
			held = frappe.db.sql(
				"""SELECT SUM(valuation_rate * actual_qty) / SUM(actual_qty) FROM `tabBin`
				   WHERE item_code = %s AND actual_qty > 0""", (code,))
			rate = flt(held[0][0]) if held and held[0][0] else 0
			item = frappe.db.get_value("Item", code, ["valuation_rate", "last_purchase_rate", "stock_uom"], as_dict=True) or {}
			rate = rate or flt(item.get("valuation_rate")) or flt(item.get("last_purchase_rate"))
			factor = 1.0
			if item.get("stock_uom") and not is_kg(item.get("stock_uom")):
				# ERPNext's factor is stock-unit quantity per 1 of the unit: 0.07 for 1 Kg of a bale.
				for uom in ("Kg", "Kilogram", "KG", "kg"):
					f = frappe.db.get_value("UOM Conversion Detail", {"parent": code, "uom": uom}, "conversion_factor")
					if f:
						factor = flt(f)
						break
			self.rates[code] = (rate, factor)
		return self.rates[code]

	def herd_costs(self, herd):
		"""{date: cost of one head's feed that day} for every recorded day of a herd."""
		if herd not in self.herds:
			rows = frappe.db.sql(
				"""SELECT fa.date, fa.head_count, i.item_code, i.uom, i.actual_kg
				   FROM `tabLivestock Feed Actual` fa
				   JOIN `tabLivestock Feed Actual Item` i ON i.parent = fa.name
				   WHERE fa.herd = %s AND fa.docstatus < 2""", (herd,), as_dict=True)
			days, heads = {}, {}
			for r in rows:
				if not r.head_count or r.head_count <= 0:
					continue
				d = str(r.date)
				heads[d] = r.head_count
				if not is_kg(r.uom):
					continue
				rate, factor = self.rate_per_stock_unit(r.item_code)
				days[d] = days.get(d, 0.0) + flt(r.actual_kg) * factor * rate
			self.herds[herd] = {d: c / heads[d] for d, c in days.items()}
		return self.herds[herd]


def _spells(animal, born, herd):
	from upande_livestock.serverscripts.animals.animal_profile import _spells as profile_spells

	events = frappe.get_all(
		"Livestock Event",
		filters={"animal": animal.name, "docstatus": 1, "event_type": "Movement"},
		fields=["event_type", "event_date", "current_herd", "new_herd"],
		order_by="event_date asc, creation asc",
	)
	spells = profile_spells(frappe._dict(date_of_birth=born, current_herd=herd), [frappe._dict(e) for e in events])
	if not spells and herd:
		spells = [{"herd": herd, "from": str(born or today()), "to": None}]
	return spells


def _value(animal, price_per_kg):
	"""(amount, source, as_of) for the bull, or (None, None, None).

	The farm's one answer to "what is he worth" is appreciation.current_value:
	the asset's book value after every adjustment, else the matrix appraisal.
	The bull price per kg x his last weight is the last resort.
	"""
	from upande_livestock.serverscripts.common.appreciation import current_value

	cv = current_value(animal.name)
	if cv.get("value") is not None and flt(cv["value"]):
		return flt(cv["value"], 2), cv["source"], today()
	if price_per_kg and flt(animal.last_weight_kg):
		return flt(price_per_kg * flt(animal.last_weight_kg), 2), "price_per_kg", today()
	return None, None, None


def _weights(animal_name, limit=12):
	rows = frappe.get_all(
		"Livestock Weight Record", filters={"animal": animal_name, "docstatus": ["<", 2]},
		fields=["weight_date", "weight_kg"], order_by="weight_date desc, creation desc", limit_page_length=limit)
	return [{"on": str(r.weight_date), "kg": flt(r.weight_kg)} for r in reversed(rows) if r.weight_date]


def _growth(animal, series):
	adg = None
	if len(series) >= 2:
		days = date_diff(series[-1]["on"], series[0]["on"])
		if days > 0:
			adg = flt((series[-1]["kg"] - series[0]["kg"]) / days, 3)
	last = series[-1] if series else None
	return {
		"kg": last["kg"] if last else (flt(animal.last_weight_kg) or None),
		"on": last["on"] if last else None,
		"adg": adg,
		"birth_kg": flt(animal.birth_weight_kg) or None,
		"series": series,
	}


def _fields():
	return ["name", "burn_name", "sex", "status", "disabled", "current_herd", "date_of_birth",
	        "asset_link", "last_weight_kg", "birth_weight_kg"]


def economics(animal, cache, price_per_kg, bulls_purpose, with_series=True):
	born = animal.date_of_birth
	start = str(born) if born else None
	spells = _spells(animal, born, animal.current_herd)
	if not start and spells:
		start = min(str(s["from"]) for s in spells)
	costs = {s["herd"]: cache.herd_costs(s["herd"]) for s in spells}
	daily = days_in(spells, costs, start or today(), today())
	amount, source, as_of = _value(animal, price_per_kg)
	total, since = accumulate(daily, amount)
	days_kept = date_diff(today(), start) if start else None
	series = _weights(animal.name) if with_series else []
	return {
		"ok": True,
		"animal": animal.name,
		"purpose": bulls_purpose,
		"kept_as_cost": bulls_purpose == "Cull for sale at birth",
		"days_kept": days_kept,
		"feed": {
			"cost": total,
			"days_fed": len(daily),
			"per_day": flt(total / len(daily), 2) if daily else None,
			"method": METHOD,
		},
		"value": {"amount": amount, "source": source, "as_of": as_of},
		"net": net_of(amount, total),
		"burden_since": since,
		"growth": _growth(animal, series) if with_series else None,
		"currency": frappe.db.get_default("currency") or "KES",
	}


def _bull(name):
	a = frappe.db.get_value("Animal", name, _fields(), as_dict=True)
	if not a:
		frappe.throw(frappe._("{0} is not an animal on this farm.").format(name))
	if (a.sex or "").strip().lower() != "male":
		frappe.throw(frappe._("{0} is not a bull.").format(name))
	return a


@frappe.whitelist()
def bull_economics(payload=None):
	"""{purpose, feed, value, net, burden_since, kept_as_cost, growth} for one bull."""

	def go():
		guard_read("Animal")
		name = (as_dict(payload).get("animal") or "").strip()
		if not name:
			frappe.throw(frappe._("Select an animal."))
		price = flt(frappe.db.get_single_value("Livestock Settings", "bull_price_per_kg"))
		return economics(_bull(name), _Cache(), price, purpose())

	return run(go, "livestock bull_economics failed")


# The endpoints split out into their own modules. Imported here so the dotted paths the phone and
# the desk already call still resolve (Frappe checks the whitelist by function identity).
# Last, because each of them imports helpers from this module.
from upande_livestock.serverscripts.animals.bull_economics_bulk import bull_economics_bulk  # noqa: E402,F401
