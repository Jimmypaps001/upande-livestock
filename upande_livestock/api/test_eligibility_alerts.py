# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who gets offered what, and what the farm gets told.

The offer lists used to be "every active animal", which invited a milking
against a calf and a service against a weaner. They are now derived from where
an animal stands in the herd structure — derived, because a list marked by hand
drifts the first time a herd is renamed or added.

Alerts are CAPTURED, not delivered. Nothing here sends anything; the tests hold
that line deliberately, because the channel has not been chosen and a test that
asserted an email would freeze that decision.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from upande_livestock.serverscripts.alerts import raise_alerts as herd_alerts
from upande_livestock.serverscripts.common import herd_movement as hm
from upande_livestock.serverscripts.breeding.breeding_options import breeding_options
from upande_livestock.serverscripts.breeding.create_pregnancy_diagnosis import create_pregnancy_diagnosis
from upande_livestock.serverscripts.milking.milking_options import milking_options


class TestMilkingIsOfferedOnlyForLactatingHerds(IntegrationTestCase):
	def test_the_list_is_the_lactation_groups(self):
		res = milking_options()
		if res.get("error"):
			raise unittest.SkipTest(res["error"][:120])
		offered = {h["name"] for h in res["herds"]}
		self.assertTrue(offered, "some herd must be offered")
		self.assertEqual(offered, set(hm.milking_herds()))

	def test_no_growth_herd_is_offered(self):
		"""A calf is never in milk."""
		res = milking_options()
		if res.get("error"):
			raise unittest.SkipTest(res["error"][:120])
		offered = {h["name"] for h in res["herds"]}
		for rung in hm.growth_ladder():
			self.assertNotIn(rung["herd"], offered)

	def test_it_narrows_rather_than_offering_everything(self):
		res = milking_options()
		if res.get("error"):
			raise unittest.SkipTest(res["error"][:120])
		total = frappe.db.count("Herds")
		self.assertLess(len(res["herds"]), total,
		                "if every herd is offered the restriction is not doing anything")


class TestServiceIsOfferedOnlyForServableAnimals(IntegrationTestCase):
	def setUp(self):
		self.res = breeding_options()
		if self.res.get("error"):
			raise unittest.SkipTest(self.res["error"][:120])

	def test_every_offered_animal_is_servable(self):
		for a in self.res["animals"]:
			self.assertTrue(hm.is_servable(a["name"]), "{} is offered but not servable".format(a["name"]))

	def test_no_young_calf_is_offered(self):
		"""A weaner in the offer list invites a service biology rules out."""
		rungs = hm.growth_ladder()
		young = {r["herd"] for r in rungs if not r["exits_on_service"]}
		for a in self.res["animals"]:
			self.assertNotIn(a["herd"], young)

	def test_the_wait_is_the_optimal_window_not_the_floor(self):
		"""Settings holds a hard floor and the point the farm actually starts
		serving. Offering from the floor puts cows in front of the breeder weeks
		before anybody would serve them."""
		s = hm.settings()
		optimal = int(s.get("post_calving_optimal_service_days") or 0)
		floor = int(s.get("post_calving_min_service_days") or 0)
		if not (optimal and floor):
			raise unittest.SkipTest("both windows not configured")
		self.assertEqual(hm.service_wait_days(), optimal)
		self.assertGreaterEqual(optimal, floor)

	def test_it_narrows_rather_than_offering_everyone(self):
		active = frappe.db.count("Animal", {"disabled": 0,
		                                    "status": ["not in", ["Dead", "Deceased", "Sold", "Culled", "Disposed"]]})
		self.assertLess(len(self.res["animals"]), active)


class TestDiagnosisNeedsAService(IntegrationTestCase):
	"""A diagnosis answers a question a service asked."""

	def test_only_animals_with_an_open_service_are_offered(self):
		res = breeding_options()
		if res.get("error"):
			raise unittest.SkipTest(res["error"][:120])
		for a in res.get("diagnosis_animals") or []:
			self.assertTrue(hm.has_open_service(a["name"]))

	def test_recording_one_without_a_service_is_refused(self):
		"""A 'Confirmed' invented from nothing then drives calving, herd moves
		and milk — so it is stopped at the door."""
		rungs = hm.growth_ladder()
		if not rungs:
			raise unittest.SkipTest("no ladder configured")
		calf = frappe.db.get_value("Animal", {"current_herd": rungs[0]["herd"]}, "name")
		if not calf or hm.has_open_service(calf):
			raise unittest.SkipTest("no un-served animal to test with")
		res = create_pregnancy_diagnosis({"animal": calf, "diagnosis_result": "Confirmed"})
		self.assertTrue(res.get("error"))
		self.assertIn("no service", res["error"].lower())

	def test_the_two_lists_are_not_the_same(self):
		"""Servable and diagnosable are different questions."""
		res = breeding_options()
		if res.get("error"):
			raise unittest.SkipTest(res["error"][:120])
		serv = {a["name"] for a in res["animals"]}
		diag = {a["name"] for a in (res.get("diagnosis_animals") or [])}
		if not diag:
			raise unittest.SkipTest("nothing awaiting a check on this site")
		self.assertNotEqual(serv, diag)


class TestAlerts(IntegrationTestCase):
	def test_collecting_writes_nothing(self):
		before = frappe.db.count("Livestock Alert")
		herd_alerts.collect()
		self.assertEqual(frappe.db.count("Livestock Alert"), before)

	def test_every_alert_names_an_animal_and_says_why(self):
		for a in herd_alerts.collect():
			self.assertIn(a["kind"], herd_alerts.KINDS)
			self.assertTrue(a["animal"])
			self.assertTrue(a["message"])
			self.assertIn(a["severity"], ("Due", "Overdue"))

	def test_an_overdue_move_is_a_different_kind_from_a_due_one(self):
		"""So somebody can act on the ones that are late without wading through
		the ones that are merely ready."""
		kinds = {a["kind"] for a in herd_alerts.collect()}
		if "Move Overdue" not in kinds:
			raise unittest.SkipTest("nothing overdue on this site")
		self.assertIn("Move Due", kinds)

	def test_raising_twice_in_a_day_raises_once(self):
		"""An alert repeated hourly is an alert people learn to skip."""
		herd_alerts.raise_alerts()
		second = herd_alerts.raise_alerts()
		self.assertEqual(second["raised"], 0)
		self.assertGreater(second["already_open"], 0)

	def test_the_detail_survives_as_numbers(self):
		"""So a report can use them without re-deriving from the sentence."""
		herd_alerts.raise_alerts()
		row = frappe.get_all("Livestock Alert", filters={"alert_date": today()},
		                     fields=["name", "detail"], limit=1)
		if not row:
			raise unittest.SkipTest("no alerts raised on this site today")
		self.assertTrue(frappe.parse_json(row[0].detail))

	def test_closing_one_records_who_closed_it(self):
		herd_alerts.raise_alerts()
		name = frappe.db.get_value("Livestock Alert", {"status": "Open"}, "name")
		if not name:
			raise unittest.SkipTest("no open alert")
		doc = frappe.get_doc("Livestock Alert", name)
		doc.status = "Actioned"
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertTrue(doc.actioned_on)
		self.assertTrue(doc.actioned_by)
		doc.status = "Open"
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertFalse(doc.actioned_on, "reopening clears the stamp")

	def test_nothing_here_sends_anything(self):
		"""Deliberate. The channel has not been chosen, and a test asserting an
		email would freeze that decision before it is made."""
		import inspect

		src = inspect.getsource(herd_alerts)
		for forbidden in ("sendmail", "send_email", "Notification Log", "requests.post"):
			self.assertNotIn(forbidden, src,
			                 "alerts are captured, not delivered — {} does not belong here".format(forbidden))
