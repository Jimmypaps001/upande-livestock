# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Weight bands: where an animal's latest weight says it belongs."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.alerts.raise_alerts import refresh_weight_alerts
from upande_livestock.serverscripts.common import weight_bands as wb
from upande_livestock.serverscripts.tests.beef_fixtures import (
	clear_bands,
	isolate,
	make_animal,
	make_herd,
	submit_weight,
)


class TestWeightBands(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		clear_bands()

	def _ladder(self):
		self.a = make_herd("ZZ Fat A", "Fattening", 150, 250).name
		self.b = make_herd("ZZ Fat B", "Fattening", 250, 350).name
		self.c = make_herd("ZZ Fat C", "Fattening", 350, 450).name

	def test_boundary_weight_goes_to_higher_band(self):
		self._ladder()
		self.assertEqual(wb.band_for_weight(250), self.b)
		self.assertEqual(wb.band_for_weight(249.9), self.a)
		self.assertIsNone(wb.band_for_weight(100))

	def test_no_bands_no_suggestions(self):
		herd = make_herd("ZZ Pen", "Other").name
		make_animal(herd, 300)
		self.assertEqual(wb.band_suggestions(), [])

	def test_heavier_than_top_band_is_ready_for_exit(self):
		self._ladder()
		animal = make_animal(self.c, 460)
		check = wb.band_check(animal.name)
		self.assertEqual((check["kind"], check["to_herd"]), ("Ready for Exit", None))

	def test_animal_in_its_band_is_left_alone(self):
		self._ladder()
		self.assertIsNone(wb.band_check(make_animal(self.a, 200).name))

	def test_outgrown_animal_is_pointed_at_the_band_that_fits(self):
		self._ladder()
		animal = make_animal(self.a, 262)
		check = wb.band_check(animal.name)
		self.assertEqual((check["kind"], check["to_herd"], check["weight_kg"]),
		                 ("Weight Band Move Due", self.b, 262))
		self.assertEqual([s["animal"] for s in wb.band_suggestions()], [animal.name])

	def test_calf_reaching_first_band_is_flagged(self):
		self._ladder()
		calves = make_herd("ZZ Calves", "Calf").name
		ready, small = make_animal(calves, 155), make_animal(calves, 90)
		self.assertEqual(wb.band_check(ready.name)["to_herd"], self.a)
		self.assertIsNone(wb.band_check(small.name))

	def test_refresh_on_submit_opens_then_settles(self):
		self._ladder()
		animal = make_animal(self.a)
		submit_weight(animal.name, 262)
		open_ = frappe.get_all("Livestock Alert", filters={
			"animal": animal.name, "alert_kind": "Weight Band Move Due", "status": "Open"},
			fields=["name", "message", "detail"])
		self.assertEqual(len(open_), 1)
		self.assertIn("suggest " + self.b, open_[0].message)
		self.assertEqual(frappe.parse_json(open_[0].detail)["to_herd"], self.b)

		frappe.db.set_value("Animal", animal.name, "current_herd", self.b)
		refresh_weight_alerts(animal.name)
		self.assertEqual(frappe.get_all("Livestock Alert", filters={
			"animal": animal.name, "alert_kind": "Weight Band Move Due", "status": "Open"}), [])

	def test_calf_heavier_than_a_closed_top_band_is_ready_for_exit(self):
		self._ladder()
		calves = make_herd("ZZ Calves", "Calf").name
		self.assertEqual(wb.band_check(make_animal(calves, 460).name)["kind"], "Ready for Exit")
		self.assertEqual(wb.band_check(make_animal(calves, 300).name)["to_herd"], self.b)

	def test_heifer_calves_are_not_flagged_for_the_fattening_ladder(self):
		self._ladder()
		calves = make_herd("ZZ Calves", "Calf").name
		self.assertIsNone(wb.band_check(make_animal(calves, 300, sex="Female").name))
		self.assertIsNone(wb.band_check(make_animal(calves, 460, sex="Female").name))
		bull = make_animal(calves, 300)
		self.assertEqual([s["animal"] for s in wb.band_suggestions()], [bull.name])

	def test_a_cancelled_only_weight_withdraws_the_alert(self):
		self._ladder()
		animal = make_animal(self.a)
		record = submit_weight(animal.name, 262)
		self.assertIsNotNone(wb.band_check(animal.name))
		record.cancel()
		self.assertIsNone(wb.band_check(animal.name))
		self.assertEqual(frappe.get_all("Livestock Alert", filters={
			"animal": animal.name, "alert_kind": "Weight Band Move Due", "status": "Open"}), [])
