# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Cancelling or deleting a service, diagnosis, calving or selection move takes back what it stamped;
write replies always carry `warnings` and name everything they created."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.breeding.create_pregnancy_diagnosis import create_pregnancy_diagnosis
from upande_livestock.serverscripts.breeding.create_service_event import create_service_event
from upande_livestock.serverscripts.breeding.record_birth import record_birth
from upande_livestock.serverscripts.movement.create_movement_event import create_movement_event
from upande_livestock.serverscripts.movement.move_animals import move_animals
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, test_employee

NOTE = "Strong Boran bull, good conformation, kept as a replacement"


def ago(days):
	return add_days(today(), -days)


def cow_state(name):
	return frappe.db.get_value("Animal", name, ["repro_status", "last_service_date", "last_calving_date",
	                                           "expected_calving_date"], as_dict=True)


class TestEventUndo(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 0)
		self.op = test_employee()
		self.group = make_herd("ZZ UN Group", "Breeding").name
		self.cow = make_animal(self.group, sex="Female", date_of_birth=ago(3000))
		self.bull = make_animal(self.group, sex="Male", date_of_birth=ago(2500))

	def _service(self):
		got = create_service_event({"animal": self.cow.name, "operator": self.op})
		self.assertTrue(got["ok"], got)
		return frappe.get_doc("Livestock Event", got["name"])

	def test_cancelling_a_service_puts_the_cow_back(self):
		before = cow_state(self.cow.name)
		svc = self._service()
		self.assertEqual(cow_state(self.cow.name).repro_status, "Served")
		svc.cancel()
		after = cow_state(self.cow.name)
		self.assertEqual((after.repro_status, after.last_service_date), ("Open", before.last_service_date))

	def test_cancelling_the_latest_of_two_services_goes_back_to_the_first(self):
		first = self._service()
		frappe.db.set_value("Livestock Event", first.name, {"pregnancy_confirmation_status": "Not Pregnant"})
		second = frappe.copy_doc(first)
		second.service_date = second.event_date = today()
		second.insert(ignore_permissions=True)
		second.submit()
		second.cancel()
		self.assertEqual(str(cow_state(self.cow.name).last_service_date), str(first.service_date))

	def test_cancelling_a_diagnosis_reopens_the_service(self):
		svc = self._service()
		dx = create_pregnancy_diagnosis({"animal": self.cow.name, "diagnosis_result": "Confirmed",
		                                 "operator": self.op, "related_service": svc.name})
		self.assertEqual(cow_state(self.cow.name).repro_status, "Pregnant")
		frappe.get_doc("Livestock Event", dx["name"]).cancel()
		self.assertEqual(frappe.db.get_value("Livestock Event", svc.name, "pregnancy_confirmation_status"), "Pending")
		self.assertEqual(cow_state(self.cow.name).repro_status, "Served")

	def test_cancelling_then_deleting_a_service_leaves_the_cow_clean(self):
		svc = self._service()
		svc.cancel()
		frappe.delete_doc("Livestock Event", svc.name, force=True, ignore_permissions=True)
		self.assertEqual(cow_state(self.cow.name).repro_status, "Open")
		self.assertIsNone(cow_state(self.cow.name).last_service_date)

	def test_cancelling_a_calving_cascades_to_births_calf_and_the_derived_pregnancy(self):
		got = record_birth({"dam": self.cow.name, "operator": self.op, "outcome": "Live Birth",
		                    "calves": [{"sex": "Male", "birth_weight": 31}]})
		self.assertTrue(got["ok"], got)
		made = got["created"]
		self.assertEqual(made["calving"], got["name"])
		self.assertEqual(len(made["births"]), 1)
		self.assertEqual(len(made["animals"]), 1)
		self.assertTrue(made["service"] and made["pregnancy_diagnosis"])
		self.assertTrue(frappe.db.exists("Animal", made["animals"][0]))
		self.assertTrue(cow_state(self.cow.name).last_calving_date)

		frappe.get_doc("Livestock Event", got["name"]).cancel()

		for birth in made["births"]:
			self.assertEqual(frappe.db.get_value("Livestock Event", birth, "docstatus"), 2)
		self.assertFalse(frappe.db.exists("Animal", made["animals"][0]))
		self.assertEqual(frappe.db.get_value("Livestock Event", made["service"], "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Livestock Event", made["pregnancy_diagnosis"], "docstatus"), 2)
		after = cow_state(self.cow.name)
		self.assertEqual((after.repro_status, after.last_calving_date, after.last_service_date),
		                 ("Open", None, None))

	def test_a_calf_with_a_history_is_not_deleted_with_its_birth(self):
		got = record_birth({"dam": self.cow.name, "operator": self.op, "outcome": "Live Birth",
		                    "calves": [{"sex": "Female", "birth_weight": 30}]})
		calf = got["created"]["animals"][0]
		from upande_livestock.serverscripts.tests.beef_fixtures import submit_weight

		submit_weight(calf, 45)
		frappe.get_doc("Livestock Event", got["name"]).cancel()
		self.assertTrue(frappe.db.exists("Animal", calf))
		self.assertEqual(frappe.db.get_value("Animal", calf, "disabled"), 1)

	def test_cancelling_a_selection_move_clears_the_stream_and_note(self):
		calves = make_herd("ZZ UN Calves", "Other").name
		bull = make_animal(calves, sex="Male", date_of_birth=ago(230))
		got = create_movement_event({"animal": bull.name, "new_herd": self.group, "operator": self.op,
		                             "remarks": NOTE})
		self.assertEqual(frappe.db.get_value("Animal", bull.name, "stream"), "Breeding")
		frappe.get_doc("Livestock Event", got["name"]).cancel()
		row = frappe.db.get_value("Animal", bull.name, ["stream", "breeding_note", "breeding_note_by",
		                                                "current_herd"], as_dict=True)
		self.assertEqual((row.stream, row.breeding_note, row.breeding_note_by, row.current_herd),
		                 ("", None, None, calves))

	def test_cancelling_a_feedlot_move_keeps_an_earlier_selection(self):
		calves = make_herd("ZZ UN Calves2", "Other").name
		pen = make_herd("ZZ UN Pen", "Fattening", 0, 0).name
		bull = make_animal(calves, sex="Male", date_of_birth=ago(230))
		create_movement_event({"animal": bull.name, "new_herd": self.group, "operator": self.op, "remarks": NOTE})
		later = create_movement_event({"animal": bull.name, "new_herd": pen, "operator": self.op})
		self.assertEqual(frappe.db.get_value("Animal", bull.name, "stream"), "Feedlot")
		frappe.get_doc("Livestock Event", later["name"]).cancel()
		self.assertEqual(frappe.db.get_value("Animal", bull.name, "stream"), "Breeding")

	def test_write_replies_always_carry_warnings(self):
		svc = create_service_event({"animal": self.cow.name, "operator": self.op})
		self.assertEqual(svc["warnings"], [])
		other = make_animal(self.group, sex="Female", date_of_birth=ago(3000))
		pd = create_pregnancy_diagnosis({"animal": other.name, "diagnosis_result": "Confirmed",
		                                 "operator": self.op, "conception_date": ago(60)})
		self.assertEqual(pd["warnings"], [])
		self.assertEqual(pd["created"]["service"], pd["service"])
		pen = make_herd("ZZ UN Pen2", "Other").name
		heifer = make_animal(self.group, sex="Female", date_of_birth=ago(700))
		mv = create_movement_event({"animal": heifer.name, "new_herd": pen, "operator": self.op})
		self.assertEqual(mv["warnings"], [])
		heifer2 = make_animal(self.group, sex="Female", date_of_birth=ago(700))
		batch = move_animals({"animals": [heifer2.name], "new_herd": pen, "operator": self.op})
		self.assertEqual(batch["warnings"], [])
		born = record_birth({"dam": other.name, "operator": self.op, "outcome": "Live Birth",
		                     "calves": [{"sex": "Female", "birth_weight": 30}]})
		self.assertEqual(born["warnings"], [])
		self.assertEqual(born["created"]["service"], None)   # her diagnosis' service was on file
