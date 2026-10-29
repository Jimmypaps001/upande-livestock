# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Mutara shoats demo: two sheep flocks and two goat herds, counted by number.

    bench --site mutara.local execute upande_livestock.demo.seed_mutara_shoats.execute

Development and demo sites only. Idempotent: every event, sample and treatment is keyed on its herd and a
`seed:` tag (or date), and the plan is a pure function of a fixed RNG seed and a fixed ANCHOR date, so a second
run changes nothing.

Per herd: an opening flock, a year of ledger events (three matings, two lambing / kidding seasons and a weaning,
deaths with causes, sales and a slaughter, ram purchases, transfers between herds of the same species, quarterly
head counts with a planted variance), monthly weight samples, a ration, five treatments (one still in
withdrawal), a paddock. Treatments issue from the Drug Store, which the seed stocks.
"""

import random
from datetime import date, timedelta

import frappe

from upande_livestock.serverscripts.common import shoats

ANCHOR = date(2026, 10, 29)
SEED = 20261029
COMPANY = "Mutara"
FARM = "Mutara"

HERDS = {   # name -> config
	"Dorper Flock": dict(species="Sheep", breed="Dorper", open=(50, 3, 4), rate=1.3, w=(52, 82, 46), paddock="Paddock A2"),
	"Red Maasai Flock": dict(species="Sheep", breed="Red Maasai", open=(40, 2, 4), rate=1.15, w=(34, 48, 30),
	                         paddock="Paddock A5"),
	"Galla Goat Herd": dict(species="Goat", breed="Galla", open=(32, 2, 2), rate=1.4, w=(42, 60, 36), paddock="Paddock A2"),
	"Boer Goat Herd": dict(species="Goat", breed="Boer", open=(38, 2, 3), rate=1.6, w=(55, 85, 48), paddock="Paddock A5"),
}
BREEDS = ["Dorper", "Red Maasai", "Galla", "Boer"]
TRANSFERS = [   # from, to, class, n, days ago
	("Dorper Flock", "Red Maasai Flock", "males", 1, 130),
	("Red Maasai Flock", "Dorper Flock", "females", 4, 60),
	("Boer Goat Herd", "Galla Goat Herd", "males", 1, 95),
]
CAUSES = ["Disease", "Predation", "Accident", "Cold or Exposure", "Poisoning", "Old Age", "Unknown"]
MATINGS = [(345, 315), (235, 205), (30, 10)]   # start, end (days ago)
COUNTS = (270, 180, 90, 14)                    # head counts (days ago)
STORE_ITEMS = {   # item -> (name, uom, qty received, rate)
	"LSK-DEW-ALB": ("Albendazole 10% Oral Drench (1 L)", "Litre", 12, 2400),
	"LSK-VAC-PPR": ("PPR Vaccine (100 dose)", "Nos", 20, 1800),
	"LSK-DIP-AMI": ("Amitraz Acaricide Dip (1 L)", "Litre", 60, 1200),
	"LSK-AB-OTC": ("Oxytetracycline LA 20% (100 ml)", "Nos", 20, 950),
}
RATION = {"Sheep": (0.8, 0.3), "Goat": (0.9, 0.4)}   # kg per head per day: hay, pellets
PELLETS, PELLET_RATE = "Mutara Shoat Pellets", 62
RECEIPT_REMARK = "Mutara shoats demo: opening drugs"


def ago(n):
	return ANCHOR - timedelta(days=int(n))


def _log(m):
	print("  " + m)


# ---------------------------------------------------------------------------
# the plan: a pure function of SEED and ANCHOR
# ---------------------------------------------------------------------------


def _rng(*key):
	return random.Random("{}:{}".format(SEED, ":".join(str(k) for k in key)))


def build_plan():
	"""{herd: {"events": [...], "samples": [...], "treatments": [...], "final": {...}}}. Events are dicts of a
	Herd Count Event, dated `days` ago, sorted oldest first, with the head they leave behind in `after`."""
	paired_in = {}
	for src, dst, k, n, days in TRANSFERS:
		paired_in.setdefault(dst, []).append((days, k, n, src))
	plan = {}
	for name, cfg in HERDS.items():
		r = _rng(name)
		f0, m0, o0 = cfg["open"]
		species = cfg["species"]
		ev = [dict(days=365, type="Purchase", females=f0, males=m0, others=o0, young=0,
		           reason="Foundation flock", amount=round((f0 * 9500 + m0 * 24000 + o0 * 6000), -2))]
		fixed_deaths = []
		for src, dst, k, n, days in TRANSFERS:
			if src == name:
				ev.append(dict(days=days, type="Transfer Out", other_herd=dst, **{k: n}, reason="Breeding exchange"))
			if dst == name:
				ev.append(dict(days=days, type="Transfer In", other_herd=src, **{k: n}, auto=True))
		ev.append(dict(days=200, type="Purchase", males=2, reason="Replacement breeding males", amount=60000))
		ev.append(dict(days=250, type="Sale", others=r.randint(3, 5), males=1, reason="Sold at Kajiado market",
		               amount=round(r.uniform(52000, 61000), -2)))
		ev.append(dict(days=120, type="Sale", females=r.randint(5, 7), reason="Culled ewes sold" if species == "Sheep"
		               else "Culled does sold", amount=round(r.uniform(55000, 70000), -2)))
		ev.append(dict(days=40, type="Slaughter", others=2, reason="Farm slaughter", amount=0))
		# matings and births
		cohort = []
		for i, (start, end) in enumerate(MATINGS, start=1):
			served = int(cfg["open"][0] * (0.82 + 0.03 * i)) - r.randint(0, 3)
			ev.append(dict(days=end, type="Mating", females=served, males=3 if i != 2 else 4, mating_start=ago(start),
			               mating_end=ago(end), key="m%d" % i, reason="Breeding season %d" % i))
			if i == 3:
				continue
			due = end - 150
			alive_total = int(round(served * cfg["rate"] * 0.9))
			dead_total = int(round(alive_total * 0.07))
			parts = r.choice([3, 4])
			for p in range(parts):
				a = alive_total // parts + (1 if p < alive_total % parts else 0)
				d = dead_total // parts + (1 if p < dead_total % parts else 0)
				ev.append(dict(days=due + 3 - p * 6, type="Birth", young=a, born_dead=d, mating_key="m%d" % i,
				               reason="Lambing" if species == "Sheep" else "Kidding"))
			cohort.append(due + 3 - (parts - 1) * 6)
		# deaths
		for n in range(11):
			ev.append(dict(days=r.randint(5, 355), type="Death", cause=r.choices(CAUSES, [5, 3, 2, 2, 1, 1, 3])[0],
			               pick=r.choices(["females", "young", "males", "others"], [5, 4, 1, 2])[0], n=r.randint(1, 3)))
		for days in COUNTS:
			ev.append(dict(days=days, type="Head Count", slip=r.choice([-2, -1, -1, 0, 1]), reason="Quarterly count"))
		# the weaning of the first season's lambs, 75 days after the last of them was born
		ev.append(dict(days=cohort[0] - 75, type="Weaning", wean=True, reason="Weaned"))
		ev.append(dict(days=cohort[0] - 105, type="Sale", wsale=True, reason="Weaners sold", amount=0))
		order = {"Purchase": 0, "Transfer In": 1, "Birth": 2, "Mating": 2, "Weaning": 3, "Head Count": 5}
		ev.sort(key=lambda e: (-e["days"], order.get(e["type"], 4)))
		# walk it: settle the figures that depend on the state, drop what cannot happen
		state, out, weaned = shoats.zero(), [], None
		for e in ev:
			e.setdefault("event_type", e["type"])
			c = {k: e.get(k, 0) for k in shoats.CLASSES}
			if e["type"] == "Death":
				k = e["pick"]
				n = min(e["n"], state[k] - (1 if k in ("females", "males") else 0))
				if n <= 0:
					continue
				c = dict(shoats.zero(), **{k: n})
				e.update(c)
			elif e["type"] == "Head Count":
				c = {k: max(0, state[k] + (e["slip"] if k == "females" else 0)) for k in shoats.CLASSES}
				e.update(c)
			elif e.get("wean"):
				y = state["young"]
				f = int(y * 0.46)
				m = int(y * 0.46)
				c = dict(females=f, males=m, others=y - f - m, young=y)
				e.update(c)
				weaned = c
			elif e.get("wsale"):
				c = dict(females=int(weaned["females"] * 0.3), males=int(weaned["males"] * 0.8),
				         others=weaned["others"], young=0)
				c = {k: min(v, max(0, state[k] - (1 if k in ("females", "males") else 0))) for k, v in c.items()}
				e.update(c)
				e["amount"] = round((c["females"] * 9000 + c["males"] * 11000 + c["others"] * 7000), -2)
			elif e["type"] in shoats.SUBS or e["type"] == "Sale":
				for k in shoats.CLASSES:
					if c[k] > state[k] - (1 if k in ("females", "males") else 0):
						c[k] = max(0, state[k] - (1 if k in ("females", "males") else 0))
				e.update(c)
				if not any(c.values()):
					continue
			state = shoats.apply(state, dict(event_type=e["type"], other_herd=e.get("other_herd"), **c))
			e["after"] = dict(state)
			out.append(e)
		for n, e in enumerate(out, start=1):
			e["tag"] = "seed:%s:%d" % (name, n)
		plan[name] = {"events": out, "final": dict(state), "cohorts": cohort,
		              "samples": [], "treatments": []}
	# weight samples, from the planned head at each date
	for name, cfg in HERDS.items():
		r = _rng(name, "weights")
		fw, mw, base = cfg["w"]
		evs = plan[name]["events"]
		for d in list(range(330, 0, -30)) + [7]:
			state = shoats.zero()
			for e in evs:
				if e["days"] >= d:
					state = e["after"]
			tot = sum(state.values())
			if not tot:
				continue
			births = [e["days"] for e in evs if e["type"] == "Birth" and e["days"] >= d]
			lamb = min(30, 4 + 0.22 * (births[-1] - d + 10)) if births and state["young"] else 18
			avg = (state["females"] * fw + state["males"] * mw + state["young"] * lamb + state["others"] * base) / tot
			avg *= 1 + r.uniform(-0.03, 0.03)
			n = min(tot, r.randint(14, 22))
			plan[name]["samples"].append(dict(days=d, cls="All", n=n, avg=round(avg, 1)))
			if d in (270, 180, 90, 7):
				if state["males"]:
					plan[name]["samples"].append(dict(days=d, cls="males", n=min(state["males"], 3),
					                                  avg=round(mw * (1 + r.uniform(-0.04, 0.04)), 1)))
				if state["young"]:
					plan[name]["samples"].append(dict(days=d, cls="young", n=min(state["young"], 10),
					                                  avg=round(lamb * (1 + r.uniform(-0.05, 0.05)), 1)))
	# treatments
	for name, cfg in HERDS.items():
		evs = plan[name]["events"]

		def head_at(d):
			s = shoats.zero()
			for e in evs:
				if e["days"] >= d:
					s = e["after"]
			return sum(s.values())

		spec = [(280, "Deworming", "LSK-DEW-ALB", 0.0075, 1.0, 14, "Routine drench"),
		        (255, "Vaccination", "LSK-VAC-PPR", 0.01, 1.0, 0, "PPR"),
		        (120, "Dipping", "LSK-DIP-AMI", 0.025, 1.0, 7, "Tick control"),
		        (45, "Treatment", "LSK-AB-OTC", 0.05, None, 28, "Pneumonia"),
		        (6, "Deworming", "LSK-DEW-ALB", 0.0075, 1.0, 14, "Routine drench")]
		for days, kind, item, dose, share, wd, why in spec:
			n = int(head_at(days) * share) if share else 6
			plan[name]["treatments"].append(dict(days=days, type=kind, item=item, dose=dose, n=n, withdrawal=wd, why=why))
	return plan


# ---------------------------------------------------------------------------
# applying the plan
# ---------------------------------------------------------------------------


def ensure_breeds():
	for b in BREEDS:
		if not frappe.db.exists("Breed", b):
			doc = frappe.new_doc("Breed")
			doc.breed = b
			doc.insert(ignore_permissions=True)
			_log("breed " + b)


def ensure_herds():
	for name, cfg in HERDS.items():
		want = {"counting": "By number", "species": cfg["species"], "breed": cfg["breed"], "herd_class": "Other"}
		if frappe.db.exists("Herds", name):
			for k, v in want.items():
				if frappe.db.get_value("Herds", name, k) != v:
					frappe.db.set_value("Herds", name, k, v)
			continue
		frappe.get_doc({"doctype": "Herds", "herd_name": name, **want}).insert(ignore_permissions=True)
		_log("herd " + name)


def ensure_paddocks():
	for name, cfg in HERDS.items():
		if not frappe.db.exists("Herds", name):
			continue
		if frappe.db.get_value("Herds", name, "paddock"):
			continue
		place = "{} - {}".format(cfg["paddock"], frappe.db.get_value("Company", COMPANY, "abbr"))
		if frappe.db.exists("Warehouse", place):
			frappe.db.set_value("Herds", name, "paddock", place)
			_log("{} placed on {}".format(name, place))


def _operator():
	return frappe.db.get_value("Employee", {"user_id": "saitoti@mutaraorchards.com"}, "name")


def apply_events(plan, operator):
	todo = sorted(((e["days"], name, e) for name, p in plan.items() for e in p["events"] if not e.get("auto")),
	              key=lambda t: (-t[0], t[1], t[2]["tag"]))
	made = 0
	for _days, herd, e in todo:
		if frappe.db.exists("Herd Count Event", {"herd": herd, "remarks": e["tag"], "docstatus": 1}):
			continue
		mating = None
		if e.get("mating_key"):
			m = [x for x in plan[herd]["events"] if x.get("key") == e["mating_key"]][0]
			mating = frappe.db.get_value("Herd Count Event", {"herd": herd, "remarks": m["tag"], "docstatus": 1}, "name")
		doc = frappe.new_doc("Herd Count Event")
		doc.update({
			"herd": herd, "event_date": str(ago(e["days"])), "event_type": e["type"], "remarks": e["tag"],
			"operator": operator, "reason": e.get("reason"), "amount": e.get("amount"), "cause": e.get("cause"),
			"other_herd": e.get("other_herd"), "born_dead": e.get("born_dead", 0), "mating": mating,
			"mating_start": str(e["mating_start"]) if e.get("mating_start") else None,
			"mating_end": str(e["mating_end"]) if e.get("mating_end") else None,
			**{k: e.get(k, 0) for k in shoats.CLASSES}})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		made += 1
		if made % 40 == 0:
			frappe.db.commit()
	frappe.db.commit()
	return made


def apply_samples(plan, operator):
	made = 0
	for herd, p in plan.items():
		for s in p["samples"]:
			on = str(ago(s["days"]))
			if frappe.db.exists("Herd Weight Sample", {"herd": herd, "sample_date": on, "sample_class": s["cls"]}):
				continue
			frappe.get_doc({"doctype": "Herd Weight Sample", "herd": herd, "sample_date": on, "sample_class": s["cls"],
			                "animals_weighed": s["n"], "average_kg": s["avg"], "operator": operator,
			                "remarks": "seed"}).insert(ignore_permissions=True)
			made += 1
	frappe.db.commit()
	return made


def ensure_drugs():
	"""The four products and their opening stock in the Drug Store."""
	from frappe.utils import flt

	from upande_livestock.upande_livestock.doctype.herd_treatment.herd_treatment import drug_store

	store = drug_store()
	if not store:
		raise RuntimeError("no Drug Store: run demo.seed_mutara_stores first")
	if not frappe.db.exists("Item Group", "DRUGS"):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": "DRUGS", "parent_item_group": "All Item Groups",
		                "is_group": 0}).insert(ignore_permissions=True)
	rows = []
	for code, (title, uom, qty, rate) in STORE_ITEMS.items():
		if not frappe.db.exists("Item", code):
			frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": title, "item_group": "DRUGS",
			                "stock_uom": uom, "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0,
			                "valuation_rate": rate, "standard_rate": rate}).insert(ignore_permissions=True)
			_log("item " + code)
		rows.append((code, qty, rate))
	if not frappe.db.exists("Stock Entry", {"remarks": RECEIPT_REMARK, "docstatus": 1}):
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = se.purpose = "Material Receipt"
		se.company = COMPANY
		se.set_posting_time = 1
		se.posting_date = ago(296)
		se.remarks = RECEIPT_REMARK
		for code, qty, rate in rows:
			se.append("items", {"item_code": code, "qty": qty, "t_warehouse": store, "basic_rate": rate})
		se.insert(ignore_permissions=True)
		se.submit()
		_log("drugs received into " + store)
	return store


def apply_treatments(plan, operator):
	from frappe.utils import cint

	made = 0
	for herd, p in plan.items():
		for t in p["treatments"]:
			on = str(ago(t["days"]))
			tag = "seed:%s:%s:%s" % (herd, t["type"], on)
			if frappe.db.exists("Herd Treatment", {"herd": herd, "remarks": tag, "docstatus": 1}):
				continue
			doc = frappe.get_doc({
				"doctype": "Herd Treatment", "herd": herd, "treatment_date": on, "treatment_type": t["type"],
				"product": t["item"], "dose_per_head": t["dose"], "number_treated": t["n"],
				"withdrawal_days": t["withdrawal"], "diagnosis": t["why"], "treated_by": operator, "remarks": tag})
			doc.flags.ignore_permissions = True
			doc.insert()
			doc.submit()
			made += 1
	frappe.db.commit()
	return made


def ensure_rations():
	from upande_livestock.serverscripts.feeding._standing_ration import set_standing_ration

	if not frappe.db.exists("Item", PELLETS):
		frappe.get_doc({"doctype": "Item", "item_code": PELLETS, "item_name": PELLETS, "item_group": "DAIRY",
		                "stock_uom": "Kilogram", "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0,
		                "include_item_in_manufacturing": 1, "valuation_rate": PELLET_RATE,
		                "standard_rate": PELLET_RATE}).insert(ignore_permissions=True)
	for name, cfg in HERDS.items():
		if frappe.db.get_value("Herds", name, "bom"):
			continue
		hay, pel = RATION[cfg["species"]]
		got = set_standing_ration(name, [{"item_code": "Mutara Boma Hay", "qty": hay}, {"item_code": PELLETS, "qty": pel}],
		                          ration_item="Ration - {}".format(name), farm=FARM)
		_log("ration {} -> {}".format(name, got["bom"]))


def counts():
	return {h: shoats.head(h)["total"] for h in HERDS}


def execute():
	"""Seed the shoats. Idempotent; prints what it does. Backdating is opened for the history load."""
	was = frappe.db.get_single_value("Livestock Settings", "custom_backdating_open")
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
	frappe.db.commit()
	try:
		_execute()
	finally:
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", was or 0)
		frappe.db.commit()


def _execute():
	plan = build_plan()
	print("seeding Mutara shoats: {} herds".format(len(plan)))
	ensure_breeds()
	ensure_herds()
	ensure_paddocks()
	frappe.db.commit()
	operator = _operator()
	_log("{} ledger events".format(apply_events(plan, operator)))
	_log("{} weight samples".format(apply_samples(plan, operator)))
	ensure_drugs()
	frappe.db.commit()
	_log("{} treatments".format(apply_treatments(plan, operator)))
	ensure_rations()
	for h in HERDS:
		shoats.rebuild(h)
	frappe.db.commit()
	print("done: {}".format(counts()))
