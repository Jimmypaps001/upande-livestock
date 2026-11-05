# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The animal's stage is ONE rule, shared by the desk and the phone's sync.

`common/animal_stage.cycle` is what `animal_profile` and `animals_since` both
ask. These tests pin the rule itself, that the two callers agree, and that a
delta sync resends an animal whose stage changed by an EVENT or by TIME even
though her Animal row was never touched."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now, today

from upande_livestock.serverscripts.animals.animal_profile import animal_profile
from upande_livestock.serverscripts.breeding.create_service_event import create_service_event
from upande_livestock.serverscripts.common import animal_stage
from upande_livestock.serverscripts.mobile.animals_since import animals_since
from upande_livestock.serverscripts.tests.test_operations import _employee, _make_cow, _purge, _purge_events_for

COW = "ZZ STAGE COW"


def _facts(**kw):
	return {"calving": None, "service": None, "confirmed": None, **kw}


def _a(**kw):
	return {"disabled": 0, "status": "Active", "sex": "Female", "date_of_birth": add_days(today(), -900), **kw}


class TestTheRule(IntegrationTestCase):
	def stage(self, facts, **a):
		return animal_stage.cycle(_a(**a), _facts(**facts))["stage"]

	def test_each_stage(self):
		d = lambda n: add_days(today(), -n)  # noqa: E731
		self.assertEqual(self.stage({}), "heifer")
		self.assertEqual(self.stage({"calving": d(10)}), "fresh")
		self.assertEqual(self.stage({"calving": d(61)}), "open")
		self.assertEqual(self.stage({"calving": d(100), "service": d(30)}), "served")
		self.assertEqual(self.stage({"calving": d(100), "service": d(60), "confirmed": d(20)}), "confirmed")
		self.assertEqual(self.stage({}, status="Sold"), "retired")
		self.assertEqual(self.stage({}, disabled=1), "retired")

	def test_a_male_never_gets_the_heifer_cycle(self):
		kind = lambda **a: animal_stage.cycle(_a(sex="Male", **a), _facts())  # noqa: E731
		self.assertEqual(kind(stream="Breeding")["stage"], "bull")
		self.assertEqual(kind(stream="Breeding")["kind"], "bull")
		self.assertEqual(kind(stream="Feedlot", last_weight_kg=90)["stage"], "calf")
		self.assertEqual(kind(stream="Feedlot", last_weight_kg=180)["stage"], "weaner")
		self.assertEqual(kind(stream="Feedlot", last_weight_kg=500)["stage"], "market")
		self.assertEqual(kind(stream="Feedlot", last_weight_kg=500)["kind"], "growth")
		# unweighed: past weaning he is a steer with no rung; a young one is a calf
		self.assertEqual(kind(stream="Feedlot")["stage"], "steer")
		self.assertEqual(kind(date_of_birth=add_days(today(), -30))["stage"], "calf")

	def test_the_ladder_climbs_with_weight(self):
		order = [animal_stage.growth_position(kg)["stage"] for kg in (50, 160, 270, 400, 460)]
		self.assertEqual(order, list(animal_stage.GROWTH_STAGES))
		pos = animal_stage.growth_position(200)
		self.assertTrue(0 < pos["pct"] < 100)
		self.assertGreater(pos["nextKg"], 200)
		self.assertIsNone(animal_stage.growth_position(460)["nextKg"])
		self.assertIsNone(animal_stage.growth_position(None))

	def test_unknown_sex_gets_no_cycle(self):
		c = animal_stage.cycle(_a(sex=None), _facts())
		self.assertEqual((c["kind"], c["stage"]), ("unknown", "unknown"))

	def test_a_young_female_is_a_calf_then_a_heifer(self):
		self.assertEqual(self.stage({}, date_of_birth=add_days(today(), -60)), "calf")
		self.assertEqual(self.stage({}), "heifer")

	def test_a_confirmation_before_the_last_calving_is_over(self):
		d = lambda n: add_days(today(), -n)  # noqa: E731
		self.assertEqual(self.stage({"calving": d(100), "confirmed": d(300)}), "open")

	def test_facts_for_reads_the_same_facts_as_an_event_list(self):
		cow = _make_cow(COW)
		self.addCleanup(self._tidy)
		got = create_service_event({"animal": cow.name, "event_date": today(), "operator": _employee(),
		                            "service_type": "Natural"})
		self.assertFalse(got.get("error"), got)
		bulk = animal_stage.facts_for([cow.name])[cow.name]
		events = frappe.get_all("Livestock Event", filters={"animal": cow.name, "docstatus": 1},
		                        fields=["event_type", "event_date", "diagnosis_result"])
		self.assertEqual(bulk, animal_stage.facts_from_events(events))
		self.assertEqual(bulk["service"], today())

	def _tidy(self):
		_purge_events_for(COW)
		_purge("Animal", COW)
		frappe.db.commit()


class TestOnThePhone(IntegrationTestCase):
	def setUp(self):
		self.cow = _make_cow(COW)
		self.addCleanup(self._tidy)

	def _tidy(self):
		_purge_events_for(COW)
		_purge("Animal", COW)
		frappe.db.commit()

	def row(self, result):
		return next((a for a in result["animals"] if a["name"] == COW), None)

	def test_every_row_carries_the_stage_the_desk_shows(self):
		rows = animals_since()["animals"]
		self.assertTrue(rows)
		self.assertTrue(all(r["stage"] for r in rows))
		for r in rows[:15] + [self.row({"animals": rows})]:
			self.assertEqual(r["stage"], animal_profile({"animal": r["name"]})["stage"], r["name"])

	def test_a_service_event_resends_her_though_the_animal_row_is_untouched(self):
		before = self.row(animals_since())
		self.assertEqual(before["stage"], "heifer")
		since = add_to_date(now(), seconds=-30)
		# Her row is older than `since`; only the event is new.
		frappe.db.set_value("Animal", COW, "modified", add_to_date(now(), hours=-5), update_modified=False)
		got = create_service_event({"animal": COW, "event_date": today(), "operator": _employee(),
		                            "service_type": "Natural"})
		self.assertFalse(got.get("error"), got)
		frappe.db.set_value("Animal", COW, "modified", add_to_date(now(), hours=-5), update_modified=False)
		delta = animals_since(since)
		self.assertEqual(self.row(delta)["stage"], "served")

	def test_an_animal_whose_fresh_window_ran_out_is_resent(self):
		frappe.db.set_value("Animal", COW, "modified", add_to_date(now(), hours=-5), update_modified=False)
		moved = animal_stage.moved_since(add_to_date(now(), days=-1))
		self.assertNotIn(COW, moved)
		# A calving 61 days ago crossed fresh -> open yesterday-or-today.
		ev = frappe.get_doc({"doctype": "Livestock Event", "event_type": "Calving", "animal": COW,
		                     "event_date": add_days(today(), -61)})
		ev.flags.ignore_validate = True
		ev.db_insert()
		frappe.db.set_value("Livestock Event", ev.name, "docstatus", 1)
		frappe.db.set_value("Livestock Event", ev.name, "modified", add_to_date(now(), days=-30), update_modified=False)
		self.assertIn(COW, animal_stage.moved_since(add_to_date(now(), days=-1)))


class TestBullStatus(IntegrationTestCase):
	def test_a_bull_alone_in_the_bull_reserve_is_at_rest(self):
		name = frappe.db.get_value("Animal", {"sex": "Male", "stream": "Breeding", "current_herd": "Bull Reserve",
		                                      "status": "Active"})
		if not name:
			self.skipTest("no breeding bull in Bull Reserve on this site")
		got = animal_stage.bull_status(name, "Bull Reserve")
		self.assertIn(got["state"], ("At rest", "In breeding cycle"))
		if frappe.db.count("Animal", {"current_herd": "Bull Reserve", "sex": "Female", "status": "Active"}) == 0:
			self.assertEqual(animal_stage.bull_status("NOBODY", "Bull Reserve")["state"], "At rest")

	def test_running_with_females_is_in_the_breeding_cycle(self):
		herd = frappe.db.sql("""select a.current_herd from tabAnimal a join tabHerds h on h.name = a.current_herd
			where h.herd_class = 'Breeding' and a.sex = 'Female' and a.status = 'Active' limit 1""")
		if not herd:
			self.skipTest("no Breeding herd with females")
		self.assertEqual(animal_stage.bull_status("NOBODY", herd[0][0])["state"], "In breeding cycle")
		self.assertEqual(animal_stage.bull_status("NOBODY", None)["state"], "At rest")


class TestProfileBySex(IntegrationTestCase):
	def profile(self, **flt_):
		name = frappe.db.get_value("Animal", {"status": "Active", "disabled": 0, **flt_})
		if not name:
			self.skipTest(f"no animal like {flt_}")
		return animal_profile({"animal": name})

	def test_feedlot_steer_has_growth_figures_no_repro_cycle(self):
		p = self.profile(sex="Male", stream="Feedlot")
		self.assertEqual(p["cycle"]["kind"], "growth")
		self.assertIn(p["stage"], animal_stage.GROWTH_STAGES + (animal_stage.UNWEIGHED_MALE,))
		self.assertNotIn(p["stage"], ("heifer", "open", "served", "confirmed", "fresh"))

	def test_breeding_bull_has_a_status(self):
		p = self.profile(sex="Male", stream="Breeding")
		self.assertEqual(p["stage"], "bull")
		self.assertIn(p["cycle"]["bull"]["state"], ("At rest", "In breeding cycle"))
		self.assertIn(p["cycle"]["class"], ("Breeding bull", "Young bull"))

	def test_a_cow_keeps_the_reproductive_cycle(self):
		p = self.profile(sex="Female", repro_status="Pregnant")
		self.assertEqual(p["cycle"]["kind"], "repro")
