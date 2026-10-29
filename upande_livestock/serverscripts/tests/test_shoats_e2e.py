# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Every Shoats endpoint the phone calls, exercised as the simulated herdsman over HTTP.

Logs in as saitoti@mutaraorchards.com against the live site (MUTARA_E2E_URL, default
https://mutara.132.145.18.63.nip.io) with the password the beef seed put in sites/<site>/site_config.json
(`mutara_sim_password`; never in code). It needs the web process running the current code (restart Mutara web
after a change) and a Drug Store holding LSK-DEW-ALB.

It works on two herds of its own, committed here so the web worker sees them, and removes them with every record
they gathered (events, samples, treatments, the stock issues behind them) when the run ends. The seeded flocks
are only read.
"""

import os
import unittest

import frappe
import requests
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

SIM_USER = "saitoti@mutaraorchards.com"
BASE = os.environ.get("MUTARA_E2E_URL", "https://mutara.132.145.18.63.nip.io").rstrip("/")
GROUP = "upande_livestock.serverscripts"
HERD = "ZZE2E Sheep Flock"
HERD2 = "ZZE2E Sheep Flock 2"
GOATS = "ZZE2E Goat Herd"
DRUG = "LSK-DEW-ALB"


def ago(days):
	return str(add_days(today(), -days))


class TestShoatsEndToEnd(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		password = frappe.conf.get("mutara_sim_password")
		if not password or not frappe.db.exists("Herds", {"counting": "By number"}):
			raise unittest.SkipTest("the Mutara shoats seed has not been run on this site")
		cls.http = requests.Session()
		got = cls.http.post(f"{BASE}/api/method/login", data={"usr": SIM_USER, "pwd": password}, timeout=60)
		if got.status_code != 200:
			raise unittest.SkipTest(f"cannot log in as {SIM_USER} at {BASE}: {got.status_code}")
		cls.clean()
		# the story is back-dated; the window is opened for the run and put back as found
		cls.backdating = frappe.db.get_single_value("Livestock Settings", "custom_backdating_open")
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
		for name, species in ((HERD, "Sheep"), (HERD2, "Sheep"), (GOATS, "Goat")):
			frappe.get_doc({"doctype": "Herds", "herd_name": name, "counting": "By number", "species": species,
			                "herd_class": "Other"}).insert(ignore_permissions=True)
		frappe.db.commit()
		cls.made = {"count_event": [], "treatment": [], "weight_sample": []}

	@classmethod
	def clean(cls):
		herds = [h for h in (HERD, HERD2, GOATS) if frappe.db.exists("Herds", h)]
		if not herds:
			return
		entries = frappe.get_all("Herd Treatment", filters={"herd": ["in", herds]}, pluck="stock_entry")
		for table in ("Herd Treatment", "Herd Count Event", "Herd Weight Sample"):
			frappe.db.sql(f"delete from `tab{table}` where herd in %s", (tuple(herds),))
		entries = [e for e in entries if e]
		if entries:
			frappe.db.sql("delete from `tabStock Ledger Entry` where voucher_no in %s", (tuple(entries),))
			frappe.db.sql("delete from `tabGL Entry` where voucher_no in %s", (tuple(entries),))
			frappe.db.sql("delete from `tabStock Entry Detail` where parent in %s", (tuple(entries),))
			frappe.db.sql("delete from `tabStock Entry` where name in %s", (tuple(entries),))
		frappe.db.sql("delete from `tabHerds` where name in %s", (tuple(herds),))
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		if getattr(cls, "http", None):
			cls.clean()
			frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", cls.backdating or 0)
			frappe.db.commit()
		super().tearDownClass()

	def call(self, path, payload=None, method="POST", **params):
		url = f"{BASE}/api/method/{GROUP}.{path}"
		if method == "GET":
			got = self.http.get(url, params=params, timeout=120)
		else:
			body = {"payload": frappe.as_json(payload)} if payload is not None else params
			got = self.http.post(url, data=body, timeout=120)
		self.assertEqual(got.status_code, 200, got.text[:500])
		frappe.db.rollback()   # end this process's read snapshot so the next read sees what the web worker committed
		return got.json().get("message")

	def ok(self, out, warns=True):
		self.assertIsInstance(out, dict, out)
		self.assertTrue(out.get("ok"), out)
		if warns:   # every shoat endpoint answers with the (usually empty) list
			self.assertIsInstance(out.get("warnings"), list, out)
		return out

	def event(self, herd, event_type, days=0, **kw):
		out = self.ok(self.call("shoats.record_count_event.record_count_event",
		                        {"herd": herd, "event_type": event_type, "event_date": ago(days), **kw}))
		self.made["count_event"].append(out["created"]["count_event"])
		return out

	# tests run in name order: the story reads top to bottom

	def test_01_the_herdsman_is_not_an_administrator(self):
		out = self.ok(self.call("settings.posting_day.posting_day", method="GET"), warns=False)
		self.assertTrue(out["is_employee"])
		self.assertNotIn("System Manager", out["roles"])

	def test_02_options(self):
		out = self.ok(self.call("shoats.shoat_options.shoat_options", method="GET"))
		self.assertEqual(out["species"], ["Sheep", "Goat"])
		self.assertEqual(out["classes"]["Goat"][0], {"key": "females", "label": "Does"})
		self.assertEqual(out["classes"]["Sheep"][1], {"key": "males", "label": "Rams"})
		names = [e["name"] for e in out["event_types"]]
		self.assertEqual(names, ["Head Count", "Birth", "Death", "Purchase", "Sale", "Slaughter", "Transfer In",
		                         "Transfer Out", "Weaning", "Mating"])
		self.assertIn("Predation", out["death_causes"])
		self.assertEqual(out["treatment_types"], ["Treatment", "Dipping", "Deworming", "Vaccination"])
		self.assertEqual(out["gestation_days"], 150)
		self.assertTrue(out["drug_store"])
		self.assertIn(DRUG, [d["item_code"] for d in out["drugs"]])
		self.assertTrue({"name", "label", "species", "head"} <= set(out["herds"][0]))
		self.assertIn(HERD, [h["name"] for h in out["herds"]])
		self.assertTrue(out["operator"])

	def test_03_the_seeded_flocks_list_with_totals(self):
		out = self.ok(self.call("shoats.shoat_herds.shoat_herds", method="GET"))
		by = {h["name"]: h for h in out["herds"]}
		for name, species in (("Dorper Flock", "Sheep"), ("Red Maasai Flock", "Sheep"),
		                      ("Galla Goat Herd", "Goat"), ("Boer Goat Herd", "Goat")):
			self.assertEqual(by[name]["species"], species)
			self.assertGreaterEqual(by[name]["head"]["total"], 60)
			self.assertLessEqual(by[name]["head"]["total"], 150)
			self.assertGreater(by[name]["live_weight_kg"], 0)
		row = by["Dorper Flock"]
		self.assertEqual(row["labels"]["females"], "Ewes")
		self.assertEqual(row["breed"], "Dorper")
		self.assertTrue(row["paddock"])
		for key in ("head", "live_weight_kg", "avg_weight_kg", "weight_date", "weight_basis", "withdrawal_until",
		            "in_withdrawal", "last_count_date", "has_ration", "next_due"):
			self.assertIn(key, row)
		self.assertEqual(set(out["totals"]), {"Sheep", "Goat", "Shoats"})
		self.assertEqual(out["totals"]["Shoats"]["head"], out["totals"]["Sheep"]["head"] + out["totals"]["Goat"]["head"])
		goats = self.ok(self.call("shoats.shoat_herds.shoat_herds", method="GET", species="Goat"))
		self.assertTrue(goats["herds"] and all(h["species"] == "Goat" for h in goats["herds"]))

	def test_04_the_seeded_detail_has_a_ledger_weights_matings_and_treatments(self):
		out = self.ok(self.call("shoats.shoat_herd.shoat_herd", method="GET", herd="Dorper Flock"))
		self.assertEqual(set(out), {"ok", "today", "herd", "ledger", "weights", "matings", "treatments", "warnings"})
		self.assertTrue(out["ledger"] and out["weights"] and out["matings"] and out["treatments"])
		self.assertEqual(sum(1 for m in out["matings"] if m["status"] == "Delivered"), 2)
		self.assertTrue(any(m["status"] == "Pending" for m in out["matings"]))
		self.assertTrue(out["herd"]["in_withdrawal"])
		led = self.ok(self.call("shoats.shoat_ledger.shoat_ledger", method="GET", herd="Dorper Flock", limit=500))
		self.assertEqual(led["head"]["total"], out["herd"]["head"]["total"])
		self.assertTrue({"Purchase", "Birth", "Death", "Sale", "Weaning", "Mating", "Head Count", "Transfer In",
		                 "Transfer Out"} <= {r["event_type"] for r in led["rows"]})
		counts = [r for r in led["rows"] if r["event_type"] == "Head Count"]
		self.assertTrue(all(r["variance"] is not None for r in counts))
		self.assertTrue(any(any(v for v in r["variance"].values()) for r in counts))
		only = self.ok(self.call("shoats.shoat_ledger.shoat_ledger", method="GET", herd="Dorper Flock",
		                         event_type="Death", limit=5))
		self.assertTrue(only["rows"] and all(r["event_type"] == "Death" and r["cause"] for r in only["rows"]))
		self.assertIn("error", self.call("shoats.shoat_herd.shoat_herd", method="GET", herd="Starters"))

	def test_05_the_breeding_overview(self):
		out = self.ok(self.call("shoats.shoat_breeding.shoat_breeding", method="GET"))
		self.assertEqual(out["gestation_days"], 150)
		self.assertTrue(out["matings"])
		m = out["matings"][0]
		for key in ("name", "herd", "species", "mating_start", "mating_end", "expected_birth_date", "days_to_due", "status",
		            "females_served", "males_in", "born_alive", "born_dead", "birth_rate_pct", "births"):
			self.assertIn(key, m)
		delivered = [x for x in out["matings"] if x["status"] == "Delivered"]
		self.assertTrue(delivered and all(x["born_alive"] > 0 for x in delivered))
		one = self.ok(self.call("shoats.shoat_breeding.shoat_breeding", method="GET", herd="Boer Goat Herd"))
		self.assertTrue(all(x["herd"] == "Boer Goat Herd" for x in one["matings"]))

	def test_06_the_ledger_records_and_refuses(self):
		self.event(HERD, "Purchase", 200, females=40, males=3, others=2, amount=380000, reason="E2E flock")
		out = self.event(HERD, "Birth", 30, young=30, born_dead=3)
		self.assertEqual(out["head"], {"females": 40, "males": 3, "young": 30, "others": 2, "total": 75})
		self.assertEqual(out["event"]["change"], 30)
		out = self.event(HERD, "Death", 20, cause="Predation", young=2, females=1, reason="hyena")
		self.assertEqual(out["head"]["total"], 72)
		refused = self.call("shoats.record_count_event.record_count_event",
		                    {"herd": HERD, "event_type": "Death", "cause": "Disease", "females": 500})
		self.assertIn("error", refused)
		self.assertEqual(self.ok(self.call("shoats.shoat_herd.shoat_herd", method="GET", herd=HERD))["herd"]["head"]["total"], 72)
		# a cattle herd is not a shoat herd
		cattle = frappe.get_all("Herds", filters={"counting": ["!=", "By number"]}, pluck="name", limit=1)[0]
		self.assertIn("error", self.call("shoats.record_count_event.record_count_event",
		                                 {"herd": cattle, "event_type": "Purchase", "females": 1}))

	def test_07_a_head_count_flags_the_variance(self):
		out = self.event(HERD, "Head Count", 10, females=37, males=3, young=28, others=2)
		self.assertEqual(out["variance"], {"females": -2, "males": 0, "young": 0, "others": 0})
		self.assertEqual(out["head"]["total"], 70)
		self.assertEqual(out["event"]["event_type"], "Head Count")

	def test_08_a_transfer_creates_both_sides(self):
		out = self.event(HERD, "Transfer Out", 8, other_herd=HERD2, females=5, males=1, reason="E2E exchange")
		self.assertTrue(out["created"]["paired_event"])
		self.made["count_event"].append(out["created"]["paired_event"])
		a = self.call("shoats.shoat_herd.shoat_herd", method="GET", herd=HERD)["herd"]["head"]
		b = self.call("shoats.shoat_herd.shoat_herd", method="GET", herd=HERD2)["herd"]["head"]
		self.assertEqual((a["total"], b["total"], b["females"], b["males"]), (64, 6, 5, 1))
		self.assertIn("error", self.call("shoats.record_count_event.record_count_event",
		                                 {"herd": HERD, "event_type": "Transfer Out", "other_herd": GOATS, "females": 1}))

	def test_09_weaning_and_sale(self):
		out = self.event(HERD, "Weaning", 5, females=12, males=13, others=3)
		self.assertEqual(out["head"]["young"], 0)
		self.assertEqual(out["head"]["total"], 64)
		out = self.event(HERD, "Sale", 3, males=10, amount=110000, reason="E2E sale")
		self.assertEqual(out["head"]["total"], 54)

	def test_10_mating_and_a_birth_linked_to_it(self):
		out = self.event(HERD, "Mating", 180, females=35, males=2, mating_start=ago(195), mating_end=ago(180))
		self.assertEqual(out["expected_birth_date"], ago(180 - 150))
		self.assertEqual(out["head"]["total"], 54)
		mating = out["created"]["count_event"]
		birth = self.event(HERD, "Birth", 28, young=20, born_dead=2)
		self.assertEqual(birth["mating"], mating)
		self.assertTrue(birth["mating_linked"])
		got = self.ok(self.call("shoats.shoat_breeding.shoat_breeding", method="GET", herd=HERD))
		row = [m for m in got["matings"] if m["name"] == mating][0]
		self.assertEqual((row["status"], row["born_alive"], row["born_dead"]), ("Delivered", 20, 2))
		self.assertEqual(row["expected_birth_date"], ago(30))

	def test_11_weight_samples_make_the_live_weight(self):
		out = self.ok(self.call("shoats.record_weight_sample.record_weight_sample",
		                        {"herd": HERD, "sample_date": ago(2), "sample_class": "All", "animals_weighed": 12,
		                         "average_kg": 31.5}))
		self.made["weight_sample"].append(out["created"]["weight_sample"])
		head = out["head"]["total"]
		self.assertEqual((out["live_weight_kg"], out["avg_weight_kg"], out["weight_basis"]),
		                 (round(head * 31.5, 1), 31.5, "herd sample"))
		self.assertEqual(out["sample"]["total_kg"], 378.0)
		males = self.ok(self.call("shoats.record_weight_sample.record_weight_sample",
		                          {"herd": HERD, "sample_date": ago(1), "sample_class": "males", "animals_weighed": 2,
		                           "average_kg": 70}))
		self.made["weight_sample"].append(males["created"]["weight_sample"])
		self.assertGreater(males["live_weight_kg"], out["live_weight_kg"])
		self.assertIn("error", self.call("shoats.record_weight_sample.record_weight_sample",
		                                 {"herd": HERD, "animals_weighed": 500, "average_kg": 30}))
		listed = {h["name"]: h for h in self.call("shoats.shoat_herds.shoat_herds", method="GET")["herds"]}
		self.assertEqual(listed[HERD]["live_weight_kg"], males["live_weight_kg"])

	def test_12_a_treatment_issues_from_the_drug_store(self):
		before = frappe.db.get_value("Bin", {"item_code": DRUG, "warehouse": self.drug_store()}, "actual_qty")
		frappe.db.rollback()
		out = self.ok(self.call("shoats.record_treatment.record_treatment", {
			"herd": HERD, "treatment_type": "Deworming", "product": DRUG, "dose_per_head": 0.0075,
			"number_treated": 40, "withdrawal_days": 14, "diagnosis": "E2E drench"}))
		self.made["treatment"].append(out["created"]["treatment"])
		self.assertTrue(out["created"]["stock_entry"])
		self.assertEqual(out["treatment"]["quantity"], 0.3)
		self.assertEqual(out["withdrawal_until"], ago(-14))
		after = frappe.db.get_value("Bin", {"item_code": DRUG, "warehouse": self.drug_store()}, "actual_qty")
		frappe.db.rollback()
		self.assertAlmostEqual(float(before) - float(after), 0.3, places=3)
		herd = self.call("shoats.shoat_herd.shoat_herd", method="GET", herd=HERD)
		self.assertTrue(herd["herd"]["in_withdrawal"])
		self.assertEqual(herd["treatments"][0]["name"], out["created"]["treatment"])
		# a sale inside the withdrawal goes through and says so
		sale = self.event(HERD, "Sale", 0, others=1, amount=5000)
		self.assertTrue(any("withdrawal" in w for w in sale["warnings"]), sale["warnings"])
		self.assertIn("error", self.call("shoats.record_treatment.record_treatment", {
			"herd": HERD, "product": DRUG, "dose_per_head": 0.0075, "number_treated": 5000}))
		self.assertIn("error", self.call("shoats.record_treatment.record_treatment", {
			"herd": HERD, "dose_per_head": 0.0075, "number_treated": 5}))

	def drug_store(self):
		return self.call("shoats.shoat_options.shoat_options", method="GET")["drug_store"]

	def test_13_the_bootstrap_marks_shoat_herds(self):
		out = self.ok(self.call("mobile.get_bootstrap_bundle.get_bootstrap_bundle"), warns=False)
		by = {h["name"]: h for h in out["herds"]}
		self.assertEqual((by["Dorper Flock"]["by_number"], by["Dorper Flock"]["species"], by["Dorper Flock"]["counting"]),
		                 (True, "Sheep", "By number"))
		self.assertEqual((by["Galla Goat Herd"]["species"], by["Starters"]["by_number"], by["Starters"]["species"]),
		                 ("Goat", False, "Cattle"))
		self.assertEqual(by[HERD]["fed_heads"], by[HERD]["heads"])
		self.assertGreater(by[HERD]["heads"], 0)

	def test_99_cancelling_takes_everything_back(self):
		treatment = self.made["treatment"][0]
		entry = frappe.db.get_value("Herd Treatment", treatment, "stock_entry")
		frappe.db.rollback()
		before = self.ok(self.call("shoats.shoat_herd.shoat_herd", method="GET", herd=HERD))["herd"]["head"]["total"]
		out = self.ok(self.call("shoats.cancel_shoat_record.cancel_shoat_record",
		                        {"kind": "treatment", "name": treatment}))
		self.assertEqual(out["cancelled"], {"kind": "treatment", "name": treatment})
		self.assertEqual(frappe.db.get_value("Stock Entry", entry, "docstatus"), 2)
		frappe.db.rollback()
		sample = self.made["weight_sample"][0]
		self.ok(self.call("shoats.cancel_shoat_record.cancel_shoat_record", {"kind": "weight_sample", "name": sample}))
		self.assertFalse(frappe.db.exists("Herd Weight Sample", sample))
		frappe.db.rollback()
		# the pair goes together: cancel the transfer's other side
		transfer_in = frappe.db.get_value("Herd Count Event", {"herd": HERD2, "event_type": "Transfer In", "docstatus": 1}, "name")
		frappe.db.rollback()
		out = self.ok(self.call("shoats.cancel_shoat_record.cancel_shoat_record",
		                        {"kind": "count_event", "name": transfer_in}))
		self.assertEqual(out["herd"], HERD2)
		self.assertEqual(out["head"]["total"], 0)
		self.assertEqual(self.call("shoats.shoat_herd.shoat_herd", method="GET", herd=HERD)["herd"]["head"]["total"],
		                 before + 6)
		# a birth with its mating cannot be unpicked from the wrong end, and the herd cannot go negative
		refused = self.call("shoats.cancel_shoat_record.cancel_shoat_record",
		                    {"kind": "count_event", "name": self.made["count_event"][0]})
		self.assertIn("error", refused)
		self.assertIn("error", self.call("shoats.cancel_shoat_record.cancel_shoat_record", {"kind": "nonsense", "name": "x"}))
		self.assertIn("error", self.call("shoats.cancel_shoat_record.cancel_shoat_record",
		                                 {"kind": "count_event", "name": "HCE-0000-99999"}))
