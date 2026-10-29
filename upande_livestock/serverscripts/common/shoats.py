# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Sheep and goats, kept by number.

A shoat herd (Herds.counting = "By number") has no Animal records. Its head, by
class, is the REPLAY of its submitted Herd Count Events in (date, creation)
order, so the figure on the herd is never typed: it is always what the ledger
says, and a cancelled or back-dated event simply changes the replay.

Classes are generic: `females` (ewes / does), `males` (rams / bucks), `young`
(lambs / kids) and `others` (wethers, unsexed). `LABELS` gives the farm's words.

  Birth, Purchase, Transfer In     add     (a Birth adds `young`, born alive)
  Death, Sale, Slaughter, Transfer Out   subtract
  Weaning                          young -> females / males / others (same herd),
                                   or out to another herd, which gets a Transfer In
  Head Count                       sets the head to the counted numbers; the
                                   difference from the ledger is its variance
  Mating                           changes nothing; it carries the dates

A replay that would take any class below zero is refused, naming the date.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

CLASSES = ("females", "males", "young", "others")
LABELS = {
	"Sheep": {"females": "Ewes", "males": "Rams", "young": "Lambs", "others": "Others"},
	"Goat": {"females": "Does", "males": "Bucks", "young": "Kids", "others": "Others"},
}
SPECIES = ("Sheep", "Goat")
ADDS = ("Birth", "Purchase", "Transfer In")
SUBS = ("Death", "Sale", "Slaughter", "Transfer Out")
EVENT_TYPES = ("Head Count", "Birth", "Death", "Purchase", "Sale", "Slaughter",
               "Transfer In", "Transfer Out", "Weaning", "Mating")
TREATMENT_TYPES = ("Treatment", "Dipping", "Deworming", "Vaccination")
SAMPLE_CLASSES = ("All", *CLASSES)

EVENT_FIELDS = ["name", "event_date", "creation", "event_type", "females", "males", "young", "others",
                "other_herd", "docstatus", "head_before", "head_after", "variance_females",
                "variance_males", "variance_young", "variance_others"]


def label(species, key):
	return LABELS.get(species or "Sheep", LABELS["Sheep"])[key]


def zero():
	return dict.fromkeys(CLASSES, 0)


def total(state):
	return sum(cint(state.get(k)) for k in CLASSES)


def is_by_number(herd):
	return frappe.db.get_value("Herds", herd, "counting") == "By number"


def species_of(herd):
	return frappe.db.get_value("Herds", herd, "species") or "Sheep"


def apply(state, ev):
	"""The head after one event. `ev` is any mapping with event_type and the four counts."""
	t = ev.get("event_type")
	c = {k: cint(ev.get(k)) for k in CLASSES}
	s = dict(state)
	if t in ADDS:
		for k in CLASSES:
			s[k] += c[k]
	elif t in SUBS:
		for k in CLASSES:
			s[k] -= c[k]
	elif t == "Weaning":
		s["young"] -= c["females"] + c["males"] + c["others"]
		if not ev.get("other_herd"):
			for k in ("females", "males", "others"):
				s[k] += c[k]
	elif t == "Head Count":
		s = dict(c)
	return s


def _key(ev):
	return (str(getdate(ev["event_date"])), str(ev.get("creation") or "9999"), ev.get("name") or "~")


def submitted(herd, drop=()):
	rows = frappe.db.sql(
		"""SELECT name, event_date, creation, event_type, females, males, young, others, other_herd,
		          head_before, head_after, variance_females, variance_males, variance_young, variance_others
		   FROM `tabHerd Count Event` WHERE herd = %s AND docstatus = 1""", (herd,), as_dict=True)
	return sorted((r for r in rows if r.name not in drop), key=_key)


def replay(herd, add=None, drop=(), check=True):
	"""Walk the ledger. Returns (final state, [(event, state after, state before)]).

	`add` is a document about to be submitted; `drop` names events about to be cancelled. With `check`, any class
	going below zero raises, naming the day and the class."""
	species = species_of(herd)
	events = submitted(herd, drop)
	if add is not None:
		events.append(frappe._dict(
			name=add.get("name") or "~new", event_date=add.get("event_date"), creation=add.get("creation") or "9999",
			**{k: add.get(k) for k in ("event_type", "other_herd", *CLASSES)}))
		events.sort(key=_key)
	state, trail = zero(), []
	for ev in events:
		before = state
		state = apply(state, ev)
		if check:
			for k in CLASSES:
				if state[k] < 0:
					frappe.throw(_("{0} on {1} would leave {2} with {3} {4}: only {5} stood in the herd then.").format(
						_(ev.event_type), frappe.utils.formatdate(ev.event_date), herd, state[k],
						label(species, k).lower(), before[k]))
		trail.append((ev, state, before))
	return state, trail


def head(herd):
	"""The current head by class (replay of submitted events), as a dict with a `total`."""
	state, _trail = replay(herd, check=False)
	return {**state, "total": total(state)}


def head_on(herd, on):
	"""The head by class after every event dated `on` or earlier."""
	on = getdate(on)
	state = zero()
	for ev in submitted(herd):
		if getdate(ev.event_date) <= on:
			state = apply(state, ev)
	return {**state, "total": total(state)}


def rebuild(herd):
	"""Write the ledger's answer onto the herd and onto its events (only what changed)."""
	state, trail = replay(herd, check=False)
	for ev, after, before in trail:
		want = {"head_before": total(before), "head_after": total(after)}
		if ev.event_type == "Head Count":
			for k in CLASSES:
				want["variance_" + k] = cint(ev.get(k)) - before[k]
		else:
			for k in CLASSES:
				want["variance_" + k] = 0
		if any(cint(ev.get(k)) != v for k, v in want.items()):
			frappe.db.set_value("Herd Count Event", ev.name, want, update_modified=False)
	counted = frappe.db.sql(
		"""SELECT MAX(event_date) FROM `tabHerd Count Event`
		   WHERE herd = %s AND docstatus = 1 AND event_type = 'Head Count'""", (herd,))
	until = frappe.db.sql(
		"""SELECT MAX(withdrawal_end) FROM `tabHerd Treatment`
		   WHERE herd = %s AND docstatus = 1 AND withdrawal_days > 0""", (herd,))
	frappe.db.set_value("Herds", herd, {
		"head_females": state["females"], "head_males": state["males"], "head_young": state["young"],
		"head_others": state["others"], "number_of_animals": total(state),
		"last_count_date": counted[0][0] if counted else None,
		"withdrawal_until": until[0][0] if until else None,
	})   # modified moves: the phone's bootstrap version is a digest of it
	return {**state, "total": total(state)}


# ---------------------------------------------------------------------------
# weight
# ---------------------------------------------------------------------------


def _latest_samples(herd, upto=None):
	cond = "AND sample_date <= %(upto)s" if upto else ""
	rows = frappe.db.sql(
		f"""SELECT name, sample_date, sample_class, animals_weighed, average_kg
		    FROM `tabHerd Weight Sample` WHERE herd = %(herd)s {cond}
		    ORDER BY sample_date DESC, creation DESC""", {"herd": herd, "upto": upto}, as_dict=True)
	out = {}
	for r in rows:
		out.setdefault(r.sample_class, r)
	return out


def live_weight(herd, hd=None, upto=None):
	"""{live_weight_kg, avg_weight_kg, weight_date, weight_basis} for a herd."""
	hd = hd or head(herd)
	samples = _latest_samples(herd, upto)
	if not samples or not hd["total"]:
		return {"live_weight_kg": 0.0, "avg_weight_kg": None, "weight_date": None, "weight_basis": "none"}
	avg, used_class, used_all = {}, False, False
	for k in CLASSES:
		own, whole = samples.get(k), samples.get("All")
		pick = own if own and (not whole or getdate(own.sample_date) >= getdate(whole.sample_date)) else whole
		if pick:
			avg[k] = flt(pick.average_kg)
			used_class |= pick is own
			used_all |= pick is whole
	covered = sum(hd[k] for k in avg)
	mean = sum(hd[k] * avg[k] for k in avg) / covered if covered else None
	if mean is None:
		# only samples for classes the herd has no head of
		pool = [flt(s.average_kg) for s in samples.values()]
		mean = sum(pool) / len(pool)
	kg = sum(hd[k] * avg.get(k, mean) for k in CLASSES)
	estimated = any(hd[k] and k not in avg for k in CLASSES)
	basis = "estimated" if estimated else "class samples" if used_class else "herd sample"
	newest = max(getdate(s.sample_date) for s in samples.values())
	return {"live_weight_kg": round(kg, 1), "avg_weight_kg": round(kg / hd["total"], 1),
	        "weight_date": str(newest), "weight_basis": basis}


def shoat_herd_numbers(herds=None):
	"""Head and live weight of every By-number herd (or the named ones), for the feed projection and the map.

	[{herd, label, species, head, females, males, young, others, live_weight_kg, avg_weight_kg|None,
	  weight_date|None, weight_basis}]. live_weight_kg is 0 when there are no samples."""
	filters = {"counting": "By number"}
	if herds is not None:
		filters["name"] = ["in", list(herds) or [""]]
	out = []
	for h in frappe.get_all("Herds", filters=filters, fields=["name", "herd_name", "species"], order_by="name asc"):
		hd = head(h.name)
		out.append({"herd": h.name, "label": h.herd_name or h.name, "species": h.species or "Sheep",
		            "head": hd["total"], **{k: hd[k] for k in CLASSES}, **live_weight(h.name, hd)})
	return out


def shoat_herd_numbers_by_name(herds=None):
	return {r["herd"]: r for r in shoat_herd_numbers(herds)}


# ---------------------------------------------------------------------------
# breeding
# ---------------------------------------------------------------------------


def gestation_days():
	from upande_livestock.serverscripts.common.timings import get_timing

	return get_timing("shoat_gestation_days")


def expected_birth(mating_end):
	return str(add_days(getdate(mating_end), gestation_days()))


def matings(herd=None, on=None):
	"""Every submitted Mating with its births: expected date, status, born alive / dead, rate."""
	on = getdate(on or today())
	filters = {"event_type": "Mating", "docstatus": 1}
	if herd:
		filters["herd"] = herd
	rows = frappe.get_all(
		"Herd Count Event", filters=filters, order_by="mating_start desc, creation desc",
		fields=["name", "herd", "mating_start", "mating_end", "expected_birth_date", "females", "males", "remarks"])
	if not rows:
		return []
	births = frappe.get_all(
		"Herd Count Event",
		filters={"event_type": "Birth", "docstatus": 1, "mating": ["in", [r.name for r in rows]]},
		fields=["name", "mating", "event_date", "young", "born_dead"], order_by="event_date asc")
	by = {}
	for b in births:
		by.setdefault(b.mating, []).append(b)
	species = {}
	out = []
	for r in rows:
		got = by.get(r.name, [])
		alive, dead = sum(cint(b.young) for b in got), sum(cint(b.born_dead) for b in got)
		due = getdate(r.expected_birth_date) if r.expected_birth_date else None
		days = (due - on).days if due else None
		if got:
			status = "Delivered"
		elif days is None:
			status = "Pending"
		elif days < -30:
			status = "Overdue"
		elif days <= 14:
			status = "Due"
		else:
			status = "Pending"
		species.setdefault(r.herd, species_of(r.herd))
		out.append({
			"name": r.name, "herd": r.herd, "species": species[r.herd],
			"mating_start": str(r.mating_start) if r.mating_start else None,
			"mating_end": str(r.mating_end) if r.mating_end else None,
			"expected_birth_date": str(due) if due else None, "days_to_due": days, "status": status,
			"females_served": cint(r.females), "males_in": cint(r.males),
			"born_alive": alive, "born_dead": dead,
			"birth_rate_pct": round(100.0 * (alive + dead) / cint(r.females), 1) if cint(r.females) and got else None,
			"births": [{"name": b.name, "date": str(b.event_date), "alive": cint(b.young), "dead": cint(b.born_dead)}
			           for b in got],
			"remarks": r.remarks or "",
		})
	return out


def mating_for_birth(herd, on):
	"""The Mating a birth on `on` most likely comes from: expected date within a window of it."""
	on = getdate(on)
	best = None
	for m in matings(herd):
		if not m["expected_birth_date"]:
			continue
		gap = (on - getdate(m["expected_birth_date"])).days
		if -30 <= gap <= 60 and (best is None or abs(gap) < best[0]):
			best = (abs(gap), m["name"])
	return best[1] if best else None


# ---------------------------------------------------------------------------
# rows the endpoints and the desk share
# ---------------------------------------------------------------------------


def event_row(ev):
	"""One ledger line, signed. `ev` is a get_all row (with event fields)."""
	sign = 1 if ev.event_type in ADDS else -1 if ev.event_type in SUBS else 0
	counts = {k: cint(ev.get(k)) for k in CLASSES}
	moved = sum(counts[k] for k in ("females", "males", "others")) if ev.event_type == "Weaning" else None
	change = (sign * sum(counts.values())) if sign else (-moved if moved and ev.get("other_herd") else 0)
	variance = None
	if ev.event_type == "Head Count":
		variance = {k: cint(ev.get("variance_" + k)) for k in CLASSES}
	return {
		"name": ev.name, "event_date": str(ev.event_date), "event_type": ev.event_type, **counts,
		"born_dead": cint(ev.get("born_dead")), "change": change, "head_after": cint(ev.get("head_after")),
		"cause": ev.get("cause") or "", "other_herd": ev.get("other_herd") or "", "paddock": ev.get("paddock") or "",
		"reason": ev.get("reason") or "", "amount": flt(ev.get("amount")), "mating": ev.get("mating") or "",
		"mating_start": str(ev.mating_start) if ev.get("mating_start") else None,
		"mating_end": str(ev.mating_end) if ev.get("mating_end") else None,
		"expected_birth_date": str(ev.expected_birth_date) if ev.get("expected_birth_date") else None,
		"variance": variance, "docstatus": cint(ev.get("docstatus")), "remarks": ev.get("remarks") or "",
		"operator": ev.get("operator") or "", "paired_event": ev.get("paired_event") or "",
	}


LEDGER_FIELDS = ["name", "herd", "event_date", "event_type", "females", "males", "young", "others", "born_dead",
                 "cause", "other_herd", "paddock", "reason", "amount", "mating", "mating_start", "mating_end",
                 "expected_birth_date", "head_after", "variance_females", "variance_males", "variance_young",
                 "variance_others", "docstatus", "remarks", "operator", "paired_event"]


def ledger(herd, event_type=None, limit=50, start=0):
	filters = {"herd": herd, "docstatus": 1}
	if event_type:
		filters["event_type"] = event_type
	rows = frappe.get_all("Herd Count Event", filters=filters, fields=LEDGER_FIELDS,
	                      order_by="event_date desc, creation desc", limit_start=cint(start), limit_page_length=cint(limit))
	return [event_row(r) for r in rows]


def sample_rows(herd, limit=12):
	rows = frappe.get_all("Herd Weight Sample", filters={"herd": herd},
	                      fields=["name", "sample_date", "sample_class", "animals_weighed", "average_kg", "total_kg"],
	                      order_by="sample_date desc, creation desc", limit_page_length=cint(limit))
	return [{"name": r.name, "sample_date": str(r.sample_date), "sample_class": r.sample_class,
	         "animals_weighed": cint(r.animals_weighed), "average_kg": flt(r.average_kg), "total_kg": flt(r.total_kg)}
	        for r in rows]


def treatment_rows(herd, limit=10):
	rows = frappe.get_all(
		"Herd Treatment", filters={"herd": herd, "docstatus": 1},
		fields=["name", "treatment_date", "treatment_type", "product", "product_name", "dose_per_head", "dose_uom",
		        "number_treated", "quantity", "withdrawal_days", "withdrawal_end", "diagnosis", "stock_entry"],
		order_by="treatment_date desc, creation desc", limit_page_length=cint(limit))
	return [{**{k: r.get(k) for k in ("name", "product", "product_name", "dose_uom", "diagnosis", "stock_entry")},
	         "treatment_date": str(r.treatment_date), "treatment_type": r.treatment_type,
	         "dose_per_head": flt(r.dose_per_head), "number_treated": cint(r.number_treated),
	         "quantity": flt(r.quantity), "withdrawal_days": cint(r.withdrawal_days),
	         "withdrawal_end": str(r.withdrawal_end) if r.withdrawal_end else None} for r in rows]


def herd_row(name):
	"""The herd card: head by class, live weight, withdrawal, breeding. (Read-only; no permission check.)"""
	h = frappe.db.get_value("Herds", name, ["name", "herd_name", "species", "breed", "bom", "cost_center",
	                                       "withdrawal_until", "last_count_date", "paddock"], as_dict=True)
	hd = head(name)
	lw = live_weight(name, hd)
	due = [m for m in matings(name) if m["status"] in ("Pending", "Due", "Overdue") and m["expected_birth_date"]]
	due.sort(key=lambda m: m["expected_birth_date"])
	until = getdate(h.withdrawal_until) if h.withdrawal_until else None
	return {
		"name": h.name, "label": h.herd_name or h.name, "species": h.species or "Sheep",
		"breed": h.breed or "", "paddock": h.paddock or "",
		"labels": LABELS.get(h.species or "Sheep", LABELS["Sheep"]),
		"head": hd, **lw,
		"withdrawal_until": str(until) if until else None,
		"in_withdrawal": bool(until and until > getdate(today())),
		"last_count_date": str(h.last_count_date) if h.last_count_date else None,
		"has_ration": bool(h.bom), "cost_center": h.cost_center or "",
		"next_due": ({"mating": due[0]["name"], "expected_birth_date": due[0]["expected_birth_date"],
		              "days_to_due": due[0]["days_to_due"], "females_served": due[0]["females_served"]}
		             if due else None),
		"mating_status": due[0]["status"] if due else None,
	}


def shoat_herd_names():
	return frappe.get_all("Herds", filters={"counting": "By number"}, pluck="name", order_by="species asc, name asc")


def totals(rows):
	out = {s: {"herds": 0, "head": 0, "live_weight_kg": 0.0} for s in (*SPECIES, "Shoats")}
	for r in rows:
		for key in (r["species"], "Shoats"):
			if key in out:
				out[key]["herds"] += 1
				out[key]["head"] += r["head"]["total"]
				out[key]["live_weight_kg"] = round(out[key]["live_weight_kg"] + r["live_weight_kg"], 1)
	for s in out.values():
		s["avg_weight_kg"] = round(s["live_weight_kg"] / s["head"], 1) if s["head"] and s["live_weight_kg"] else None
	return out
