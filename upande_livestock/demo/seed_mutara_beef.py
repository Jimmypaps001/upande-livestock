# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Mutara beef demo: 500 animals that exercise feedlot bands, calf separation,
natural service with sire inference, breeding bulls and the inbreeding warnings.

    bench --site mutara.local execute upande_livestock.demo.seed_mutara_beef.execute

Development and demo sites only. Idempotent: every animal, event and weight is
keyed on its tag and date, and the plan is a pure function of a fixed RNG seed
and a fixed ANCHOR date (never today()), so a second run changes nothing.

207 females and 293 males
-------------------------
Herd               class      females  males   notes
Weaner Heifers     Other         37      -
Bulling Heifers    Breeding      50      2     heifers 15-24 mo; bulls B_a (the old LG1 sire) and B_g
Lactation Group 1  Breeding      50      2     cows 3-9 y; bulls B_b, B_c
Lactation Group 2  Breeding      40      2     cows 3-9 y; bulls B_d, B_e
Bull Reserve       Breeding       -      4     2 mature, 2 young selected (with notes)
Starters/Growers/Finishers  Fattening  -  90/70/90
Calves (63: 30 F + 33 M) live in their mother's herd (LG1/LG2) until they are moved.

Deviations from the first plan, all forced by arithmetic (90 cows cannot have borne
250 feedlot bulls in two years): the feedlot bulls and 47 of the 50 bulling heifers are
Purchased with no parents; the animals born here are the 63 calves, the 37 weaner
heifers, the 3 planted bulling heifers and the 2 young reserve bulls, each through a
real Service -> Pregnancy Diagnosis -> Calving -> Birth chain. Calves, born into their
mother's herd, are Calf Separation Due when they reach the separation age.

Planted kinship cases (see `planted()`):
 1. B_a, in Bulling Heifers, sired 3 of the heifers there          (sire-daughter)
 2. young reserve bull Y1's dam is a Lactation Group 2 cow           (dam-son on moving him there)
 3. Y2 (reserve) and heifer D1/D2 share a sire; Y2 and heifer H3 share dam and sire
                                                                     (half- / full siblings)
 4. two LG2 cows served while two bulls overlapped                   (two candidate sires)
"""

import random
from datetime import date, timedelta

import frappe

ANCHOR = date(2026, 10, 29)
SEED = 20261029
SIM_USER = "saitoti@mutaraorchards.com"
OPERATOR_NAME = "Saitoti Herdsman"

LG1, LG2 = "Lactation Group 1", "Lactation Group 2"
BH, WEANERS, RESERVE = "Bulling Heifers", "Weaner Heifers", "Bull Reserve"
STARTERS, GROWERS, FINISHERS = "Starters", "Growers", "Finishers"
HERDS = [  # name, class, min kg, max kg, target adg
	(WEANERS, "Other", 0, 0, 0.7),
	(BH, "Breeding", 0, 0, 0),
	(LG1, "Breeding", 0, 0, 0),
	(LG2, "Breeding", 0, 0, 0),
	(RESERVE, "Breeding", 0, 0, 0),
	(STARTERS, "Fattening", 0, 250, 0.9),
	(GROWERS, "Fattening", 250, 280, 0.9),
	(FINISHERS, "Fattening", 280, 0, 0.9),
]
BREEDS = ["Boran", "Sahiwal", "Simmental", "Boran x Simmental"]
BURN_NAMES = ["Kito", "Simba", "Moran", "Laibon", "Ole Kina", "Sidai", "Tumaini", "Nkoilale", "Mzee", "Jabali"]
SELECTION_NOTES = {
	"Y1": "Boran-Simmental bull calf, deep body and straight topline, dam a heavy milker; kept as a replacement sire.",
	"Y2": "Strong Boran bull, good scrotal development and docile; selected from the weaners to replace an old sire.",
}


def ago(n):
	return ANCHOR - timedelta(days=int(n))


# ---------------------------------------------------------------------------
# the plan: a pure function of SEED and ANCHOR
# ---------------------------------------------------------------------------


class Plan:
	def __init__(self):
		self.rng = random.Random(SEED)
		self.animals = {}      # tag -> dict
		self.order = []        # creation order of directly created animals
		self.chains = []       # service -> PD -> calving -> birth, each creating a calf
		self.services = []     # cow services outside a calving chain (pregnant / pending)
		self.moves = []        # (tag, days_ago, to_herd, note)
		self.weights = {}      # tag -> dict(final, adg, gap)
		self.counters = {}
		self.cows = []
		self.bulls = {}
		self.herd_of = {}
		self.planted = {}

	def tag(self, sex, dob_ago):
		yy = ago(dob_ago).year % 100
		prefix = "A" if sex == "Female" else "B"
		n = self.counters.get((prefix, yy), 0) + 1
		self.counters[(prefix, yy)] = n
		return "{}{:03d}/{:02d}".format(prefix, n, yy)

	def breed(self):
		return self.rng.choices(BREEDS, weights=[50, 15, 5, 30])[0]

	def add(self, tag, sex, dob_ago, herd, **extra):
		a = {"tag": tag, "sex": sex, "dob_ago": dob_ago, "herd": herd, "breed": self.breed(),
		     "origin": "Purchased", "dam": None, "burn": tag, **extra}
		self.animals[tag] = a
		return a


def build_plan():
	p = Plan()
	r = p.rng

	# ---- bulls -----------------------------------------------------------
	names = list(BURN_NAMES)

	def bull(key, dob_ago, herd, **extra):
		a = p.add(p.tag("Male", dob_ago), "Male", dob_ago, herd, stream="Breeding", burn=names.pop(0),
		          role="bull", **extra)
		p.bulls[key] = a["tag"]
		p.order.append(a["tag"])
		return a

	bull("a", 2600, LG1, acq=2700)
	bull("b", 2300, RESERVE, acq=2400)
	bull("c", 2100, RESERVE, acq=2200)
	bull("d", 2650, LG2, acq=2750)
	bull("e", 1900, RESERVE, acq=2000)
	bull("g", 2000, RESERVE, acq=2100)
	bull("m1", 2200, RESERVE, acq=2300)
	bull("m2", 2400, RESERVE, acq=2500)
	B = p.bulls
	# rotation, as dated Movements (days ago)
	p.moves += [
		(B["a"], 300, BH, None), (B["b"], 300, LG1, None), (B["c"], 7, LG1, None),
		(B["e"], 150, LG2, None), (B["e"], 100, RESERVE, None), (B["e"], 7, LG2, None),
		(B["g"], 7, BH, None),
	]

	# ---- cows ------------------------------------------------------------
	class Cow:
		def __init__(self, tag, herd):
			self.tag, self.herd, self.births, self.concs = tag, herd, [], []

	for herd, n in ((LG1, 50), (LG2, 40)):
		for _ in range(n):
			dob = r.randint(1300, 3300)
			t = p.tag("Female", dob)
			p.add(t, "Female", dob, herd, role="cow", acq=r.randint(1110, min(dob - 1, 1300)))
			p.order.append(t)
			p.cows.append(Cow(t, herd))
	cows = {c.tag: c for c in p.cows}
	lg1 = [c for c in p.cows if c.herd == LG1]
	lg2 = [c for c in p.cows if c.herd == LG2]
	# the planted cows get early, long-held acquisition dates
	for c in lg1[:4] + lg2[:3]:
		p.animals[c.tag]["acq"] = 1250
		p.animals[c.tag]["dob_ago"] = max(p.animals[c.tag]["dob_ago"], 1500)

	def conc_ok(herd, a):
		"""Is a conception `a` days ago unambiguous in `herd`'s bull history?"""
		if herd == LG1:
			return abs(a - 300) > 12
		return not (88 <= a <= 162) and abs(a - 7) > 12

	def free(cow, conc, birth):
		return all(abs(conc - c) >= 345 and abs(birth - b) >= 345 for c, b in zip(cow.concs, cow.births))

	def pick(pool, conc, birth):
		ok = [c for c in pool if free(c, conc, birth)]
		if not ok:
			raise RuntimeError("no free cow for a birth {} days ago".format(birth))
		ok.sort(key=lambda c: (len(c.births), c.tag))
		best = [c for c in ok if len(c.births) == len(ok[0].births)]
		return r.choice(best)

	def schedule(pool, birth, sex, **extra):
		"""A calf born `birth` days ago to a cow in `pool`; the conception is chosen to be unambiguous."""
		for _ in range(200):
			conc = birth + 280 + r.randint(-6, 8)
			if not conc_ok(pool[0].herd, conc):
				birth += 1
				continue
			cow = pick(pool, conc, birth)
			cow.births.append(birth)
			cow.concs.append(conc)
			t = p.tag(sex, birth)
			a = p.add(t, sex, birth, cow.herd, origin="Born on Farm", dam=cow.tag, **extra)
			p.chains.append({"cow": cow.tag, "conc": conc, "birth": birth, "calf": t})
			return a
		raise RuntimeError("could not schedule a birth")

	# planted cases first, on the planted cows -------------------------------
	x = lg1[0]                         # Y2's and H3's dam
	y2_birth, h3_birth = 820, 480
	for birth in (y2_birth, h3_birth):
		x.births.append(birth)
		x.concs.append(birth + 281)
	y2 = p.add(p.tag("Male", y2_birth), "Male", y2_birth, LG1, origin="Born on Farm", dam=x.tag,
	           stream="Breeding", burn=names.pop(0), role="young")
	h3 = p.add(p.tag("Female", h3_birth), "Female", h3_birth, LG1, origin="Born on Farm", dam=x.tag, role="heifer")
	p.chains += [{"cow": x.tag, "conc": y2_birth + 281, "birth": y2_birth, "calf": y2["tag"]},
	             {"cow": x.tag, "conc": h3_birth + 281, "birth": h3_birth, "calf": h3["tag"]}]
	d1 = schedule([lg1[1]], 640, "Female", role="heifer")
	d2 = schedule(lg1[2:4], 590, "Female", role="heifer")
	y1 = schedule([lg2[0]], 650, "Male", stream="Breeding", role="young", burn=names.pop(0))
	p.planted = {
		"sire_daughter": {"bull": B["a"], "heifers": [d1["tag"], d2["tag"], h3["tag"]]},
		"dam_son": {"bull": y1["tag"], "dam": lg2[0].tag, "herd": LG2},
		"half_siblings": {"bull": y2["tag"], "heifers": [d1["tag"], d2["tag"]], "shared_sire": B["a"]},
		"full_siblings": {"bull": y2["tag"], "heifer": h3["tag"], "dam": x.tag, "sire": B["a"]},
		"two_candidates": {"cows": [lg2[1].tag, lg2[2].tag], "bulls": [B["d"], B["e"]], "herd": LG2,
		                   "conceptions": [130, 124]},
	}
	# two LG2 cows served while B_d and B_e overlapped; confirmed in calf
	for cow, a in ((lg2[1], 130), (lg2[2], 124)):
		p.services.append({"cow": cow.tag, "conc": a, "pd": True})

	# selection moves for the young bulls (dated, with the herdsman's note)
	p.moves += [(y2["tag"], y2_birth - 420, RESERVE, SELECTION_NOTES["Y2"]),
	            (y1["tag"], 650 - 400, RESERVE, SELECTION_NOTES["Y1"])]
	# heifer moves: dam herd -> weaners at ~220 days -> bulling heifers at 450 days
	for t in (d1["tag"], d2["tag"], h3["tag"]):
		a = p.animals[t]
		p.moves += [(t, a["dob_ago"] - 220, WEANERS, None), (t, a["dob_ago"] - 450, BH, None)]

	# ---- the rest of the animals born here ------------------------------
	avoid = {c.tag for c in lg1[:4] + lg2[:3]}
	lg1_free = [c for c in lg1 if c.tag not in avoid]
	lg2_free = [c for c in lg2 if c.tag not in avoid]

	# 37 weaner heifers (8-15 months), dams from LG2 only: half of them are the older ones
	# (their dams can calve again soon enough to bear this year's calves)
	for i in range(37):
		birth = r.randint(432, 450) if i % 2 == 0 else r.randint(250, 384)
		a = schedule(lg2_free, birth, "Female", role="weaner")
		p.moves.append((a["tag"], a["dob_ago"] - r.randint(215, 235), WEANERS, None))
	# 63 calves: 30 females, 33 males; a dozen past 210 days
	ages = [r.randint(213, 238) for _ in range(12)] + [r.randint(30, 85) for _ in range(20)] \
		+ [r.randint(106, 205) for _ in range(31)]
	r.shuffle(ages)
	sexes = ["Female"] * 30 + ["Male"] * 33
	r.shuffle(sexes)
	calf_pool = [c for c in lg1 + lg2 if c.tag not in avoid]
	for birth, sex in sorted(zip(ages, sexes), reverse=True):
		schedule(calf_pool, birth, sex, role="calf")

	# ---- bought-in heifers and bulls ------------------------------------
	for _ in range(47):
		dob = r.randint(460, 730)
		a = p.add(p.tag("Female", dob), "Female", dob, BH, role="heifer", acq=min(dob - 1, r.randint(300, 440)))
		p.order.append(a["tag"])
	for herd, n, lo, hi in ((STARTERS, 90, 245, 365), (GROWERS, 70, 365, 450), (FINISHERS, 90, 450, 730)):
		for _ in range(n):
			dob = r.randint(lo, hi)
			a = p.add(p.tag("Male", dob), "Male", dob, herd, role="feedlot", acq=min(dob - 1, r.randint(100, 240)),
			          stream="Feedlot")
			p.order.append(a["tag"])

	# ---- pregnancies outside the calving chains ----------------------------
	planted_cows = {c["cow"] for c in p.services}
	candidates = []
	for c in p.cows:
		if c.tag in planted_cows:
			continue
		last = min(c.births) if c.births else None
		if last is not None and last >= 205:
			continue                      # left open on purpose: open too long
		upper = (last - 52) if last is not None else 250
		upper = min(upper, 250)
		if upper < 45:
			continue
		candidates.append((c, upper))
	r.shuffle(candidates)
	target = 54 - len(p.services)
	# six cows served 12-34 days ago, still awaiting their pregnancy check
	waiting = [(c, u) for c, u in candidates if u >= 20][:6]
	for c, upper in waiting:
		p.services.append({"cow": c.tag, "conc": r.randint(12, min(34, upper)), "pd": False})
	for c, upper in candidates:
		if target <= 0:
			break
		if (c, upper) in waiting:
			continue
		for _ in range(100):
			a = r.randint(45, upper)
			if conc_ok(c.herd, a):
				p.services.append({"cow": c.tag, "conc": a, "pd": True})
				target -= 1
				break

	# ---- weights -----------------------------------------------------------
	overdue = set(r.sample([t for t, a in p.animals.items() if a["role"] in ("feedlot", "heifer")], 10))
	for t, a in p.animals.items():
		role = a["role"]
		gap = r.randint(45, 70) if t in overdue else r.randint(0, 27)
		if role == "cow":
			final, adg = r.uniform(380, 480), r.uniform(-0.05, 0.15)
		elif role == "bull":
			final, adg = r.uniform(650, 800), r.uniform(0.0, 0.2)
		elif role == "young":
			final, adg = r.uniform(450, 560), r.uniform(0.3, 0.6)
		elif role == "calf":
			adg = r.uniform(0.6, 1.0)
			final = min(220, max(40, 33 + adg * (a["dob_ago"] - gap)))
		elif role == "weaner":
			final, adg = r.uniform(180, 300), r.uniform(0.5, 0.9)
		elif role == "heifer":
			final, adg = r.uniform(280, 380), r.uniform(0.5, 0.9)
		else:  # feedlot
			lo, hi = {STARTERS: (170, 249), GROWERS: (251, 279), FINISHERS: (281, 440)}[a["herd"]]
			final = r.uniform(lo, hi)
			adg = r.uniform(0.8, 1.4) if a["herd"] == FINISHERS else r.uniform(0.5, 1.3)
		p.weights[t] = {"final": round(final, 1), "adg": round(adg, 3), "gap": gap}
	# poor gainers, band edge cases, exit-ready bulls
	feed = {h: [t for t, a in p.animals.items() if a["role"] == "feedlot" and a["herd"] == h]
	        for h in (STARTERS, GROWERS, FINISHERS)}
	for t in feed[GROWERS][:6]:
		p.weights[t]["adg"] = round(r.uniform(0.2, 0.39), 3)
	for t, w in zip(feed[STARTERS][:3], (251.0, 254.5, 258.0)):
		p.weights[t].update(final=w, gap=min(p.weights[t]["gap"], 20))
	for t, w in zip(feed[GROWERS][6:8], (281.0, 285.0)):
		p.weights[t].update(final=w, gap=min(p.weights[t]["gap"], 20))
	p.weights[feed[GROWERS][8]].update(final=250.0, gap=3)
	p.weights[feed[FINISHERS][0]].update(final=280.0, gap=3)
	for t, w in zip(feed[FINISHERS][1:3], (452.0, 468.5)):
		p.weights[t].update(final=w, gap=min(p.weights[t]["gap"], 20))
	p.planted["weights"] = {
		"starters_over_band": feed[STARTERS][:3], "growers_over_band": feed[GROWERS][6:8],
		"grower_exactly_250": feed[GROWERS][8], "finisher_exactly_280": feed[FINISHERS][0],
		"exit_ready": feed[FINISHERS][1:3],
	}
	p.planted["open_cows"] = [c.tag for c in p.cows if c.births and 205 <= min(c.births) <= 240]
	p.planted["dozen_past_210"] = [c["calf"] for c in p.chains
	                               if 210 < c["birth"] < 240 and p.animals[c["calf"]]["role"] == "calf"]
	return p


def planted():
	"""The tags of the planted cases (a pure function of the plan)."""
	return build_plan().planted


# ---------------------------------------------------------------------------
# applying the plan
# ---------------------------------------------------------------------------

COMPANY = "Mutara"
SIM_ROLES = ("Livestock Attendant", "Livestock Breeder", "Livestock Manager")
FEED_ITEMS = (("Mutara Boma Hay", 8), ("Mutara Maize Silage", 14), ("Mutara Beef Meal", 4))
FEED_ITEMS_RATE = (("Mutara Boma Hay", 18), ("Mutara Maize Silage", 9), ("Mutara Beef Meal", 55))


def _rng(tag, salt=""):
	return random.Random("{}:{}:{}".format(SEED, tag, salt))


def _log(message):
	print("  " + message)


def ensure_breeds():
	for name in BREEDS:
		if not frappe.db.exists("Breed", name):
			doc = frappe.new_doc("Breed")
			doc.breed = name
			doc.insert(ignore_permissions=True)
			_log("breed " + name)


def ensure_herds():
	for name, cls, lo, hi, adg in HERDS:   # low band first, so the ladder tiles at every step
		if frappe.db.exists("Herds", name):
			continue
		frappe.get_doc({"doctype": "Herds", "herd_name": name, "herd_class": cls,
		                "min_weight_kg": lo, "max_weight_kg": hi, "target_adg_kg": adg}).insert(ignore_permissions=True)
		_log("herd " + name)


def ensure_settings():
	if not frappe.db.get_single_value("Livestock Settings", "custom_default_company"):
		frappe.db.set_single_value("Livestock Settings", "custom_default_company", COMPANY)
	have = set(frappe.get_all("Livestock Heifer Herd", filters={"parent": "Livestock Settings"}, pluck="herd"))
	for idx, herd in enumerate((WEANERS, BH), start=1):
		if herd in have:
			continue
		row = frappe.new_doc("Livestock Heifer Herd")
		row.update({"herd": herd, "parent": "Livestock Settings", "parenttype": "Livestock Settings",
		            "parentfield": "heifer_herds", "idx": idx})
		row.insert(ignore_permissions=True)
	frappe.clear_document_cache("Livestock Settings", "Livestock Settings")


def ensure_sim_user():
	"""The simulated herdsman: a System User linked to an Employee, holding the herdsman
	(Attendant, Breeder) and manager roles. The password is NOT in code: it lives in
	sites/<site>/site_config.json as `mutara_sim_password` (generated here on first run)."""
	from frappe.installer import update_site_config
	from frappe.utils.password import update_password

	created = False
	if not frappe.db.exists("User", SIM_USER):
		frappe.get_doc({
			"doctype": "User", "email": SIM_USER, "first_name": "Saitoti", "last_name": "Herdsman",
			"user_type": "System User", "enabled": 1, "send_welcome_email": 0,
			"roles": [{"role": r} for r in SIM_ROLES],
		}).insert(ignore_permissions=True)
		created = True
		_log("user " + SIM_USER)
	user = frappe.get_doc("User", SIM_USER)
	have = {r.role for r in user.roles}
	for role in SIM_ROLES:
		if role not in have:
			user.append("roles", {"role": role})
	if not user.enabled:
		user.enabled = 1
	user.save(ignore_permissions=True)

	employee = frappe.db.get_value("Employee", {"user_id": SIM_USER}, "name")
	if not employee:
		employee = frappe.get_doc({
			"doctype": "Employee", "first_name": "Saitoti", "last_name": "Herdsman", "gender": "Male",
			"date_of_birth": "1990-03-15", "date_of_joining": "2024-01-01", "status": "Active",
			"company": COMPANY, "user_id": SIM_USER,
		}).insert(ignore_permissions=True).name
		_log("employee " + employee)

	password = frappe.conf.get("mutara_sim_password")
	if not password:
		password = frappe.generate_hash(length=20)
		update_site_config("mutara_sim_password", password)
		frappe.conf.mutara_sim_password = password
		created = True
	if created:
		update_password(SIM_USER, password)
		_log("password set from sites/{}/site_config.json (mutara_sim_password)".format(frappe.local.site))
	return employee


def _event(etype, animal, on, operator, **fields):
	doc = frappe.get_doc({
		"doctype": "Livestock Event", "event_type": etype, "animal": animal, "event_date": str(on),
		"operator": operator, "custom_is_backdated": 1 if on < date.today() else 0, **fields})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def _find(etype, animal, on, **extra):
	return frappe.db.get_value("Livestock Event", {
		"event_type": etype, "animal": animal, "event_date": str(on), "docstatus": 1, **extra}, "name")


def create_animal(a):
	tag = a["tag"]
	if frappe.db.exists("Animal", tag):
		return False
	repro = "Bull" if a["sex"] == "Male" and a["role"] in ("bull", "young") else \
		"Heifer" if a["sex"] == "Female" and a["role"] != "cow" else "Open"
	frappe.get_doc({
		"doctype": "Animal", "tag_number": tag, "burn_name": a["burn"], "sex": a["sex"], "breed": a["breed"],
		"species": "Cattle", "date_of_birth": ago(a["dob_ago"]), "origin": a["origin"],
		"acquisition_date": ago(a.get("acq") or a["dob_ago"]), "current_herd": a["herd"], "company": COMPANY,
		"status": "Active", "repro_status": repro, "dam": a.get("dam"), "stream": a.get("stream") or "",
	}).insert(ignore_permissions=True)
	return True


def apply_move(plan, tag, days, herd, note, operator):
	on = ago(days)
	if _find("Movement", tag, on, new_herd=herd):
		return
	was = frappe.db.get_value("Animal", tag, "current_herd")
	if was == herd:
		return
	_event("Movement", tag, on, operator, current_herd=was or "", new_herd=herd,
	       remarks=note or "Seed: {}".format("selected for breeding" if herd == RESERVE else "moved"))


def apply_chain(plan, chain, operator):
	from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births
	from upande_livestock.serverscripts.common import natural_service
	from upande_livestock.serverscripts.common.events import new_livestock_event

	calf = plan.animals[chain["calf"]]
	if frappe.db.exists("Animal", calf["tag"]):
		return
	cow, conc, birth = chain["cow"], ago(chain["conc"]), ago(chain["birth"])
	service = _find("Service", cow, conc) or natural_service.create_natural_service(
		cow, conc, operator=operator, remarks="Seed: natural service").name
	pd_on = ago(chain["conc"] - 45)
	if not _find("Pregnancy Diagnosis", cow, pd_on):
		dx = new_livestock_event({"animal": cow, "operator": operator, "event_date": str(pd_on),
		                          "remarks": "Seed: pregnancy confirmed"},
		                         "Pregnancy Diagnosis", date_key="diagnosis_date", derived=True)
		dx.diagnosis_date = dx.event_date
		dx.diagnosis_result = "Confirmed"
		dx.related_service = service
		dx.insert(ignore_permissions=True)
		dx.submit()
	calving = _find("Calving", cow, birth)
	if not calving:
		doc = new_livestock_event({"animal": cow, "operator": operator, "event_date": str(birth)},
		                          "Calving", derived=True)
		doc.current_herd = frappe.db.get_value("Animal", cow, "current_herd")
		doc.custom_calving_outcome = "Live Birth"
		doc.custom_no_of_calves = 1
		doc.custom_related_pregnancy = service
		doc.insert(ignore_permissions=True)
		doc.submit()
		calving = doc.name
	got = record_calf_births({"calving": calving, "calves": [{
		"tag": calf["tag"], "sex": calf["sex"], "breed": calf["breed"], "burn_name": calf["burn"],
		"birth_weight": round(_rng(calf["tag"], "bw").uniform(28, 38), 1), "health_status": "Healthy"}]})
	if got.get("error"):
		raise RuntimeError("{}: {}".format(calf["tag"], got["error"]))
	repro = "Bull" if calf["role"] == "young" else "Heifer" if calf["sex"] == "Female" and calf["role"] != "calf" \
		else "Calf"
	frappe.db.set_value("Animal", calf["tag"], {"repro_status": repro, "burn_name": calf["burn"]},
	                    update_modified=False)


def apply_service(plan, svc, operator):
	from upande_livestock.serverscripts.common import natural_service
	from upande_livestock.serverscripts.common.events import new_livestock_event

	conc = ago(svc["conc"])
	service = _find("Service", svc["cow"], conc) or natural_service.create_natural_service(
		svc["cow"], conc, operator=operator, remarks="Seed: natural service").name
	if not svc["pd"]:
		return
	pd_on = ago(max(svc["conc"] - 45, 0))
	if _find("Pregnancy Diagnosis", svc["cow"], pd_on):
		return
	dx = new_livestock_event({"animal": svc["cow"], "operator": operator, "event_date": str(pd_on),
	                          "remarks": "Seed: pregnancy confirmed"},
	                         "Pregnancy Diagnosis", date_key="diagnosis_date", derived=True)
	dx.diagnosis_date = dx.event_date
	dx.diagnosis_result = "Confirmed"
	dx.related_service = service
	dx.insert(ignore_permissions=True)
	dx.submit()


def apply_weights(plan, tag):
	a, w = plan.animals[tag], plan.weights[tag]
	rng = _rng(tag, "weights")
	row = frappe.db.get_value("Animal", tag, ["date_of_birth", "acquisition_date"], as_dict=True)
	earliest = max(date.fromisoformat(str(row.date_of_birth)) + timedelta(days=10),
	               date.fromisoformat(str(row.acquisition_date)))
	count = rng.randint(3, 5)
	days = [w["gap"] + 30 * i + (rng.randint(-3, 3) if i else 0) for i in range(count)]
	made = 0
	for d in sorted(set(days), reverse=True):
		on = ago(d)
		if on < earliest:
			continue
		if frappe.db.exists("Livestock Weight Record", {"animal": tag, "weight_date": str(on), "docstatus": 1}):
			continue
		kg = max(30.0, w["final"] - w["adg"] * (d - w["gap"]))
		if d == w["gap"]:
			kg = w["final"]
		doc = frappe.get_doc({
			"doctype": "Livestock Weight Record", "animal": tag, "weight_date": str(on),
			"weight_kg": round(kg, 1), "method": "Platform Scale",
			"custom_is_backdated": 1 if on < date.today() else 0})
		doc.insert(ignore_permissions=True)
		doc.submit()
		made += 1
	return made


def ensure_ai():
	"""A demo semen item in a demo store, for the A.I. option (demo/seed_test_stock)."""
	from upande_livestock.demo import seed_test_stock

	from frappe.utils import flt

	if not frappe.db.exists("Item Group", seed_test_stock.DRUG_ITEM_GROUP):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": seed_test_stock.DRUG_ITEM_GROUP,
		                "parent_item_group": "All Item Groups", "is_group": 0}).insert(ignore_permissions=True)
	made = seed_test_stock.run(receive=False)
	warehouse, item = made["warehouse"], seed_test_stock.SEMEN_ITEM_CODE
	if flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty")) > 0:
		return
	# Dated inside the site's fiscal year (seed_test_stock's own receipt is a year back).
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = se.purpose = "Material Receipt"
	se.company = COMPANY
	se.set_posting_time = 1
	se.posting_date = ago(300)
	se.remarks = "Mutara beef demo: A.I. straws"
	se.append("items", {"item_code": item, "qty": 20, "t_warehouse": warehouse, "basic_rate": 2500})
	se.insert(ignore_permissions=True)
	se.submit()
	_log("20 A.I. straws of {} received into {}".format(item, warehouse))


RATIONS = {   # herd -> (kg per head per day, hay share, silage share, meal share)
	WEANERS: (7, 0.5, 0.3, 0.2), BH: (10, 0.4, 0.4, 0.2), LG1: (12, 0.35, 0.5, 0.15),
	LG2: (12, 0.35, 0.5, 0.15), RESERVE: (11, 0.4, 0.4, 0.2), STARTERS: (6, 0.3, 0.3, 0.4),
	GROWERS: (8, 0.25, 0.4, 0.35), FINISHERS: (10, 0.2, 0.35, 0.45),
}


def ensure_rations():
	"""One standing ration per herd, through the same function the Rations page uses.

	Feed items are demo items in the DAIRY group (where the feed catalogue looks); a bull eats one head of his herd's
	ration, and calves with their mothers are not fed it (calf_separation.fed_head_count)."""
	from upande_livestock.serverscripts.feeding._standing_ration import set_standing_ration

	if not frappe.db.exists("UOM", "Kilogram"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Kilogram"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item Group", "DAIRY"):     # where the feed catalogue looks for feed
		frappe.get_doc({"doctype": "Item Group", "item_group_name": "DAIRY", "parent_item_group": "All Item Groups",
		                "is_group": 0}).insert(ignore_permissions=True)
	for name, _per in FEED_ITEMS:
		if not frappe.db.exists("Item", name):
			frappe.get_doc({"doctype": "Item", "item_code": name, "item_name": name, "item_group": "DAIRY",
			                "stock_uom": "Kilogram", "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0,
			                "include_item_in_manufacturing": 1, "valuation_rate": dict(FEED_ITEMS_RATE)[name],
			                "standard_rate": dict(FEED_ITEMS_RATE)[name]}).insert(ignore_permissions=True)
	farm = frappe.db.get_value("Warehouse", "Livestock Drug Store - {}".format(
		frappe.db.get_value("Company", COMPANY, "abbr")), "custom_farm")
	for herd, (kg, hay, silage, meal) in RATIONS.items():
		if frappe.db.get_value("Herds", herd, "bom"):
			continue
		lines = [{"item_code": FEED_ITEMS[0][0], "qty": round(kg * hay, 3)},
		         {"item_code": FEED_ITEMS[1][0], "qty": round(kg * silage, 3)},
		         {"item_code": FEED_ITEMS[2][0], "qty": round(kg - round(kg * hay, 3) - round(kg * silage, 3), 3)}]
		got = set_standing_ration(herd, lines, ration_item="Ration - {}".format(herd), farm=farm)
		_log("ration {} -> {}".format(herd, got["bom"]))


def recount():
	from upande_livestock.serverscripts.common.animal import recompute_herd_count

	for herd in frappe.get_all("Herds", pluck="name"):
		recompute_herd_count(herd)


def counts():
	rows = frappe.db.sql("SELECT sex, COUNT(*) FROM `tabAnimal` WHERE status='Active' GROUP BY sex")
	return dict(rows)


def execute(skip_stock=False):
	"""Seed Mutara. Idempotent; prints what it does.

	The history load runs with Backdating Open switched on (the age and interval
	guards are only waived for backdated records while that window is open) and
	puts the setting back as it found it, even if the run fails.
	"""
	was = frappe.db.get_single_value("Livestock Settings", "custom_backdating_open")
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
	frappe.db.commit()
	try:
		_execute(skip_stock)
	finally:
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", was or 0)
		frappe.db.commit()


def _execute(skip_stock=False):
	plan = build_plan()
	print("seeding Mutara beef: {} animals ({} chains, {} services)".format(
		len(plan.animals), len(plan.chains), len(plan.services)))
	ensure_breeds()
	ensure_herds()
	ensure_settings()
	operator = ensure_sim_user()
	frappe.db.commit()

	created = sum(1 for tag in plan.order if create_animal(plan.animals[tag]))
	frappe.db.commit()
	print("  {} animals created directly".format(created))

	bulls = set(plan.bulls.values())
	for tag, days, herd, note in sorted((m for m in plan.moves if m[0] in bulls), key=lambda m: -m[1]):
		apply_move(plan, tag, days, herd, note, operator)
	frappe.db.commit()

	for n, chain in enumerate(sorted(plan.chains, key=lambda c: -c["conc"]), start=1):
		apply_chain(plan, chain, operator)
		if n % 25 == 0:
			frappe.db.commit()
			print("  {} calving chains".format(n))
	frappe.db.commit()
	# the calves' moves before the cows' services: a young bull who has not yet been moved out of his
	# birth herd would still count as a candidate sire
	for tag, days, herd, note in sorted((m for m in plan.moves if m[0] not in bulls), key=lambda m: -m[1]):
		apply_move(plan, tag, days, herd, note, operator)
	frappe.db.commit()
	for svc in plan.services:
		apply_service(plan, svc, operator)
	frappe.db.commit()
	print("  chains, services and moves done")

	made = 0
	for n, tag in enumerate(plan.animals, start=1):
		made += apply_weights(plan, tag) or 0
		if n % 50 == 0:
			frappe.db.commit()
	frappe.db.commit()
	print("  {} weight records".format(made))

	recount()
	if not skip_stock:
		ensure_ai()
		ensure_rations()
		frappe.db.commit()
	from upande_livestock.serverscripts.alerts import raise_alerts

	raised, existing = raise_alerts.record(raise_alerts.collect())
	frappe.db.commit()
	print("  alerts: {} raised, {} already open".format(raised, existing))
	print("done: {}".format(counts()))
