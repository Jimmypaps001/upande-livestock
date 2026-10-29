# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Inbreeding is a Warn: the move goes through, the warning names the relation and the shared parent."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.alerts import raise_alerts
from upande_livestock.serverscripts.movement.create_movement_event import create_movement_event
from upande_livestock.serverscripts.movement.kinship_check import kinship_check
from upande_livestock.serverscripts.movement.move_animals import move_animals
from upande_livestock.serverscripts.tests.beef_fixtures import (
	isolate, make_animal, make_herd, test_employee,
)

NOTE = "Strong Boran bull, good conformation, kept as a replacement"


def ago(days):
	return add_days(today(), -days)


class TestKinshipWarnings(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.op = test_employee()
		self.pen = make_herd("ZZ KW Holding", "Other").name
		self.group = make_herd("ZZ KW Group", "Breeding").name
		self.cow = make_animal(self.pen, sex="Female", date_of_birth=ago(2800))
		self.bull = make_animal(self.pen, sex="Male", date_of_birth=ago(1800), stream="Breeding")
		self.daughter = make_animal(self.group, sex="Female", date_of_birth=ago(600),
		                            sire=self.bull.name, dam=self.cow.name)
		self.stranger = make_animal(self.group, sex="Female", date_of_birth=ago(900))

	def _move(self, animal, herd, **extra):
		return create_movement_event({"animal": animal.name, "new_herd": herd, "operator": self.op, **extra})

	def test_bull_into_his_daughters_herd_warns_and_moves(self):
		got = self._move(self.bull, self.group, remarks=NOTE)
		self.assertTrue(got["ok"], got)
		self.assertEqual(frappe.db.get_value("Animal", self.bull.name, "current_herd"), self.group)
		self.assertEqual(len(got["warnings"]), 1)
		self.assertIn("sire of", got["warnings"][0])
		self.assertIn(self.bull.name, got["warnings"][0])
		saved = frappe.db.get_value("Livestock Event", got["name"], "kinship_warnings")
		self.assertEqual(saved, got["warnings"][0])

	def test_female_into_her_fathers_herd_warns(self):
		bull_herd = make_herd("ZZ KW Bulls", "Breeding").name
		self._move(self.bull, bull_herd, remarks=NOTE)
		got = self._move(self.daughter, bull_herd)
		self.assertTrue(got["ok"], got)
		self.assertIn("sire of", got["warnings"][0])

	def test_half_sibling_warning_names_the_shared_parent(self):
		bull_herd = make_herd("ZZ KW Bulls2", "Breeding").name
		half_brother = make_animal(self.pen, sex="Male", date_of_birth=ago(700), sire=self.bull.name)
		got = self._move(half_brother, self.group, remarks=NOTE)
		self.assertIn("half-siblings", got["warnings"][0])
		self.assertIn("sired by " + self.bull.name, got["warnings"][0])
		self.assertTrue(bull_herd)

	def test_unrelated_move_has_no_warnings(self):
		stranger_bull = make_animal(self.pen, sex="Male", date_of_birth=ago(1800))
		got = self._move(stranger_bull, self.group, remarks=NOTE)
		self.assertTrue(got["ok"])
		self.assertEqual(got["warnings"], [])

	def test_kinship_check_off_in_settings_silences_it(self):
		frappe.db.set_single_value("Livestock Settings", "kinship_check", 0)
		got = self._move(self.bull, self.group, remarks=NOTE)
		self.assertEqual(got["warnings"], [])

	def test_move_animals_returns_every_warning(self):
		second = make_animal(self.pen, sex="Male", date_of_birth=ago(1800), stream="Breeding")
		make_animal(self.group, sex="Female", date_of_birth=ago(500), sire=second.name)
		got = move_animals({"animals": [self.bull.name, second.name], "new_herd": self.group,
		                    "operator": self.op, "remarks_by_animal": {self.bull.name: NOTE, second.name: NOTE}})
		self.assertTrue(got["ok"], got)
		self.assertEqual(len(got["warnings"]), 2)

	def test_preview_matches_the_write(self):
		got = kinship_check(self.bull.name, self.group)
		self.assertTrue(got["ok"])
		self.assertEqual([c["relation"] for c in got["conflicts"]], ["sire-daughter"])
		self.assertEqual(got["conflicts"][0]["shared_parent"], self.bull.name)
		self.assertTrue(got["note_required"])  # he comes from a holding pen: a selection
		self.assertEqual(len(got["warnings"]), 1)
		# nothing moved
		self.assertEqual(frappe.db.get_value("Animal", self.bull.name, "current_herd"), self.pen)

	def test_preview_says_a_young_bull_needs_a_note(self):
		young = make_animal(self.pen, sex="Male", date_of_birth=ago(250))
		got = kinship_check(young.name, self.group)
		self.assertEqual((got["selection"], got["note_required"], got["stream"]), (True, True, "Breeding"))

	def test_nightly_sweep_opens_and_settles_inbreeding_risk(self):
		# the bull already runs with his daughter; no move announced it
		frappe.db.set_value("Animal", self.bull.name, "current_herd", self.group)
		found = [a for a in raise_alerts.collect() if a["kind"] == "Inbreeding Risk"
		         and a["animal"] in (self.bull.name, self.daughter.name)]
		self.assertEqual(len(found), 1)
		self.assertIn("sire of", found[0]["message"])
		raise_alerts.record(raise_alerts.collect())
		open_rows = frappe.get_all("Livestock Alert", filters={"alert_kind": "Inbreeding Risk", "status": "Open",
		                           "animal": ["in", [self.bull.name, self.daughter.name]]})
		self.assertEqual(len(open_rows), 1)
		# either leaves the herd: settled
		frappe.db.set_value("Animal", self.bull.name, "current_herd", self.pen)
		raise_alerts.record(raise_alerts.collect())
		self.assertEqual(frappe.get_all("Livestock Alert", filters={
			"alert_kind": "Inbreeding Risk", "status": "Open",
			"animal": ["in", [self.bull.name, self.daughter.name]]}), [])
