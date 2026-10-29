# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Every endpoint the Mutara phone calls, exercised as the simulated herdsman over HTTP.

Logs in as saitoti@mutaraorchards.com against the live site (MUTARA_E2E_URL,
default https://mutara.132.145.18.63.nip.io) with the password the seed put in
sites/<site>/site_config.json (`mutara_sim_password`; never in code), and drives
the same calls the app makes. It needs the seeded site and the web process
running the current code (restart Mutara web after a change).

It works on animals of its own, made and committed here and removed with every
record they gathered when the run ends, so the seeded herd is untouched.
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
NOTE = "E2E bull: deep body, good feet and temperament, kept to run with the heifers"


def ago(days):
	return add_days(today(), -days)


class TestMutaraMobileEndToEnd(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		password = frappe.conf.get("mutara_sim_password")
		if not password or not frappe.db.exists("Herds", "Lactation Group 1"):
			raise unittest.SkipTest("the Mutara seed has not been run on this site")
		cls.http = requests.Session()
		got = cls.http.post(f"{BASE}/api/method/login", data={"usr": SIM_USER, "pwd": password}, timeout=60)
		if got.status_code != 200:
			raise unittest.SkipTest(f"cannot log in as {SIM_USER} at {BASE}: {got.status_code}")
		cls.made_animals = []
		frappe.db.commit()
		cls.cow = cls._animal("Female", ago(3000), "Lactation Group 1")
		cls.heifer = cls._animal("Female", ago(700), "Bulling Heifers")
		cls.calf = cls._animal("Male", ago(215), "Lactation Group 1", dam=cls.cow)
		cls.young = cls._animal("Male", ago(300), "Weaner Heifers")

	@classmethod
	def _animal(cls, sex, dob, herd, **extra):
		tag = "ZZE2E" + frappe.generate_hash(length=6).upper()
		frappe.get_doc({
			"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": sex, "date_of_birth": dob,
			"acquisition_date": dob, "current_herd": herd, "company": "Mutara", "status": "Active",
			"origin": "Purchased", **extra}).insert(ignore_permissions=True)
		frappe.db.commit()
		cls.made_animals.append(tag)
		return tag

	@classmethod
	def tearDownClass(cls):
		names = cls.made_animals
		if names:
			events = frappe.get_all(
				"Livestock Event", filters=[["animal", "in", names]], pluck="name")
			# a Calving's calf is an Animal this run did not name
			calves = frappe.get_all("Animal", filters=[["dam", "in", names]], pluck="name")
			everyone = list(dict.fromkeys(names + calves))
			events += frappe.get_all(
				"Livestock Event", filters=[["animal", "in", everyone]], pluck="name")
			events += frappe.get_all("Livestock Event", filters=[["dam", "in", names]], pluck="name")
			events = list(dict.fromkeys(events))
			for table, field in (("Livestock Weight Record", "animal"), ("Livestock Alert", "animal")):
				frappe.db.sql(f"delete from `tab{table}` where `{field}` in %s", (tuple(everyone),))
			if events:
				frappe.db.sql("delete from `tabToDo` where reference_type='Livestock Event' and reference_name in %s",
				              (tuple(events),))
				frappe.db.sql("delete from `tabLivestock Event` where name in %s", (tuple(events),))
			frappe.db.sql("delete from `tabAnimal` where name in %s", (tuple(everyone),))
			for herd in frappe.get_all("Herds", pluck="name"):
				from upande_livestock.serverscripts.common.animal import recompute_herd_count

				recompute_herd_count(herd)
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
		# end this process's read snapshot, so the next read sees what the web worker committed
		frappe.db.rollback()
		return got.json().get("message")

	def ok(self, out):
		self.assertIsInstance(out, dict, out)
		self.assertTrue(out.get("ok"), out)
		return out

	# -- reads -----------------------------------------------------------

	def test_01_the_phone_wakes_as_a_herdsman(self):
		out = self.ok(self.call("settings.posting_day.posting_day", method="GET"))
		self.assertTrue(out["is_employee"])
		self.assertTrue({"Livestock Attendant", "Livestock Breeder", "Livestock Manager"} <= set(out["roles"]))
		self.assertNotIn("System Manager", out["roles"])

	def test_02_the_bootstrap_bundle_marks_the_breeding_herds(self):
		out = self.ok(self.call("mobile.get_bootstrap_bundle.get_bootstrap_bundle"))
		herds = {h["name"]: h for h in out["herds"]}
		self.assertTrue(herds["Lactation Group 1"]["is_breeding"])
		self.assertEqual(herds["Lactation Group 1"]["herd_class"], "Breeding")
		self.assertFalse(herds["Starters"]["is_breeding"])
		self.assertGreaterEqual(herds["Lactation Group 1"]["bulls"], 2)
		for key in ("females", "bulls", "calves", "fed_heads", "heads"):
			self.assertIn(key, herds["Lactation Group 1"])
		self.assertEqual(out["settings"]["default_service_type"], "Natural")
		self.assertEqual(out["settings"]["calf_separation_age_days"], 210)

	def test_03_eligibility_names_breeding_herds_and_the_calves_due_to_leave(self):
		out = self.ok(self.call("movement.eligibility.eligibility", method="GET"))
		self.assertIn("Lactation Group 1", out["breeding_herds"])
		self.assertIn("Lactation Group 1", out["service_herds"])
		due = {c["animal"]: c for c in out["separation_due"]}
		self.assertIn(self.calf, due)
		streams = [o["stream"] for o in due[self.calf]["options"]]
		self.assertEqual(streams, ["Feedlot", "Breeding"])
		self.assertGreaterEqual(len(due), 12)

	def test_04_animal_lists_load(self):
		out = self.call("mobile.animals_since.animals_since", method="GET")
		self.assertTrue(out.get("ok", True), out)
		self.ok(self.call("mobile.get_animal_bundle.get_animal_bundle", method="GET", herd="Lactation Group 1"))

	def test_05_the_bootstrap_head_counts_leave_the_calves_unfed(self):
		out = self.ok(self.call("mobile.get_bootstrap_bundle.get_bootstrap_bundle"))
		row = {h["name"]: h for h in out["herds"]}["Lactation Group 1"]
		self.assertEqual(row["fed_heads"], row["heads"] - row["calves"])
		self.assertGreater(row["calves"], 0)

	def test_06_settings_read(self):
		out = self.ok(self.call("settings.livestock_settings.livestock_settings", method="GET"))
		self.assertEqual(out["values"]["calf_separation_age_days"], 210)

	# -- previews ---------------------------------------------------------

	def test_07_kinship_preview_flags_a_dam_and_son_and_the_note(self):
		planted = _planted()
		dam_son = planted["dam_son"]
		out = self.ok(self.call("movement.kinship_check.kinship_check", method="GET",
		                        animal=dam_son["bull"], herd=dam_son["herd"]))
		self.assertEqual([c["relation"] for c in out["conflicts"]], ["dam-son"])
		self.assertEqual(out["conflicts"][0]["shared_parent"], dam_son["dam"])
		self.assertTrue(out["warnings"])
		young = self.ok(self.call("movement.kinship_check.kinship_check", method="GET",
		                          animal=self.young, herd="Bull Reserve"))
		self.assertTrue(young["note_required"])
		self.assertEqual(young["stream"], "Breeding")

	def test_08_sire_preview_names_the_one_bull_and_lists_two(self):
		one = self.ok(self.call("breeding.sire_candidates.sire_candidates", method="GET",
		                        animal=self.cow, conception_date=ago(100)))
		self.assertTrue(one["inferred"])
		self.assertTrue(one["sire_animal"])
		two = _planted()["two_candidates"]
		got = self.ok(self.call("breeding.sire_candidates.sire_candidates", method="GET",
		                        animal=two["cows"][0], conception_date=ago(two["conceptions"][0])))
		self.assertFalse(got["inferred"])
		self.assertEqual(sorted(c["animal"] for c in got["candidates"]), sorted(two["bulls"]))

	# -- writes: the order matters, so one test walks it ----------------------

	def test_09_the_recording_walk(self):
		rec = "mobile.record_animal_event.record_animal_event"
		# weight, one animal, then a session: each / platform
		out = self.ok(self.call(rec, {"type": "Weight Recording", "animal": self.heifer, "weight_kg": 331.5,
		                              "method": "Platform Scale"}))
		self.assertEqual(out["type"], "Weight Recording")
		each = self.ok(self.call("weights.record_weights.record_weights", {
			"method": "Platform Scale", "weights": [{"animal": self.cow, "weight_kg": 441}]}))
		self.assertEqual(len(each["recorded"]), 1)
		platform = self.ok(self.call("weights.record_weights.record_weights", {
			"group": {"animals": [self.calf, self.young], "total_weight_kg": 410}}))
		self.assertEqual(len(platform["recorded"]), 2)

		# natural service from a perceived conception date (diagnosis with no service on file)
		pd = self.ok(self.call(rec, {"type": "Pregnancy Diagnosis", "animal": self.cow,
		                             "diagnosis_result": "Confirmed", "conception_date": ago(100)}))
		self.assertTrue(pd["service_created"])
		self.assertTrue(pd["sire_inferred"])
		self.assertTrue(pd["sire_animal"])
		self.assertEqual(frappe.db.get_value("Livestock Event", pd["service"], "service_type"), "Natural")

		# calving: the service is on file now; the calf gets the sire and lives in its mother's herd
		born = self.ok(self.call(rec, {"type": "Calving", "dam": self.cow, "outcome": "Live Birth",
		                               "event_date": today(),
		                               "calves": [{"sex": "Female", "birth_weight": 31}]}))
		calf_name = born["calves"][0]["animal"]
		self.made_animals.append(calf_name)
		row = frappe.db.get_value("Animal", calf_name, ["sire", "dam", "current_herd"], as_dict=True)
		self.assertEqual((row.sire, row.dam, row.current_herd), (pd["sire_animal"], self.cow, "Lactation Group 1"))

		# natural service entry with the date seen (a heifer, today) and a user-picked sire
		heifer_sire = frappe.db.get_value("Animal", {"current_herd": "Lactation Group 1", "sex": "Male"}, "name")
		svc = self.ok(self.call(rec, {"type": "Service", "animal": self.heifer, "sire_animal": heifer_sire}))
		self.assertEqual((svc["service_type"], svc["sire_animal"], svc["sire_inferred"]), ("Natural", heifer_sire, False))

		# movement: calf to Starters (no note), a young male to the reserve (note required, then given)
		mv = self.ok(self.call(rec, {"type": "Movement", "animal": self.calf, "new_herd": "Starters"}))
		self.assertEqual(mv["stream"], "Feedlot")
		refused = self.call(rec, {"type": "Movement", "animal": self.young, "new_herd": "Bull Reserve"})
		self.assertIn("Describe the bull", refused["error"])
		sel = self.ok(self.call(rec, {"type": "Movement", "animal": self.young, "new_herd": "Bull Reserve",
		                              "remarks": NOTE}))
		self.assertEqual(sel["stream"], "Breeding")
		note = frappe.db.get_value("Animal", self.young, ["breeding_note", "breeding_note_by", "stream"], as_dict=True)
		self.assertEqual((note.breeding_note, note.stream), (NOTE, "Breeding"))
		self.assertTrue(note.breeding_note_by)

		# a warned move: the planted dam-son pair (moving an animal of our own, related to a seeded cow)
		dam = _planted()["dam_son"]["dam"]
		son = self._animal("Male", ago(600), "Bull Reserve", dam=dam, stream="Breeding")
		warned = self.ok(self.call(rec, {"type": "Movement", "animal": son, "new_herd": "Lactation Group 2"}))
		self.assertTrue(any("dam of" in w for w in warned["warnings"]), warned)

		# batch move needs a note per selected bull
		batch = self.call("movement.move_animals.move_animals", {"animals": [self.heifer], "new_herd": "Weaner Heifers"})
		self.assertTrue(batch.get("ok"), batch)

	def test_10_a_user_with_no_employee_stays_view_only(self):
		user = "zz.e2e.nonemployee@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "E2E", "send_welcome_email": 0,
			                "roles": [{"role": "Livestock Attendant"}]}).insert(ignore_permissions=True)
		from frappe.utils.password import update_password

		pwd = frappe.generate_hash(length=16)
		update_password(user, pwd)
		frappe.db.commit()
		try:
			other = requests.Session()
			other.post(f"{BASE}/api/method/login", data={"usr": user, "pwd": pwd}, timeout=60)
			got = other.post(f"{BASE}/api/method/{GROUP}.mobile.record_animal_event.record_animal_event",
			                 data={"payload": frappe.as_json({"type": "Movement", "animal": self.heifer,
			                                                   "new_herd": "Weaner Heifers"})}, timeout=60)
			self.assertEqual(got.json()["message"].get("code"), "not_employee")
		finally:
			frappe.delete_doc("User", user, force=True, ignore_permissions=True)
			frappe.db.commit()


def _planted():
	from upande_livestock.demo.seed_mutara_beef import planted

	return planted()
