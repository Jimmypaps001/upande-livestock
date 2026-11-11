# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""An event type the farm switched off (Settings → Events).

For some farms a pregnancy diagnosis is not a must. Switched off, an event:

* is refused by the server when someone records a new one — unless the write
  is plumbing for another event (the retro birth path's history-only movement,
  a calving's births);
* raises no alert and fills no worklist that would prompt for it, and an alert
  already open is not shown;
* is named in the phone's bootstrap, so the phone hides it offline;
* takes the retro birth path's optional diagnosis step with it, whatever the
  back-recording setting says;
* is still listed on the Settings screen, with its stock rule and timings, so
  it can be switched back on as it was.

The migration patch switches every existing type on.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import birth_window, event_types
from upande_livestock.serverscripts.tests.beef_fixtures import isolate

EVENT_TYPE = "Livestock Event Type"
PD = "Pregnancy Diagnosis"


def switch(name, on):
	frappe.db.set_value(EVENT_TYPE, name, "is_active", 1 if on else 0)
	event_types.forget()


class EventSwitchCase(unittest.TestCase):
	def setUp(self):
		if not frappe.db.exists(EVENT_TYPE, PD):
			self.skipTest("no Pregnancy Diagnosis event type on this site")
		isolate(self)
		self.addCleanup(event_types.forget)
		event_types.forget()


class TestTheServerRefusesADisabledEvent(EventSwitchCase):
	def _new(self, **flags):
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = PD
		doc.event_date = frappe.utils.today()
		for k, v in flags.items():
			doc.flags[k] = v
		return doc

	def test_a_new_event_of_a_disabled_type_is_refused_in_words(self):
		switch(PD, False)
		with self.assertRaises(frappe.ValidationError) as caught:
			self._new().insert(ignore_permissions=True)
		self.assertIn("switched off", str(caught.exception))
		self.assertIn("Settings → Events", str(caught.exception))

	def test_an_enabled_type_is_not_refused_for_it(self):
		switch(PD, True)
		with self.assertRaises(Exception) as caught:
			# Refused for something else (no animal, no operator) — not the switch.
			self._new().insert(ignore_permissions=True)
		self.assertNotIn("switched off", str(caught.exception))

	def test_internal_plumbing_is_not_refused_for_it(self):
		switch(PD, False)
		with self.assertRaises(Exception) as caught:
			self._new(ignore_event_enabled=True).insert(ignore_permissions=True)
		self.assertNotIn("switched off", str(caught.exception))

	def test_the_helpers_read_the_switch(self):
		switch(PD, False)
		self.assertFalse(event_types.is_enabled(PD))
		self.assertIn(PD, event_types.disabled_events())
		self.assertTrue(event_types.is_enabled(""))
		switch(PD, True)
		self.assertTrue(event_types.is_enabled(PD))


class TestAlertsSkipADisabledEvent(EventSwitchCase):
	def test_alert_kinds_follow_their_event(self):
		switch(PD, False)
		self.assertFalse(event_types.alert_wanted("Pregnancy Check Overdue"))
		# An alert about the animal, not prompting for an event, stays.
		self.assertTrue(event_types.alert_wanted("Cow Open Too Long"))
		switch(PD, True)
		self.assertTrue(event_types.alert_wanted("Pregnancy Check Overdue"))

	def test_no_pregnancy_check_is_owed_with_pd_off(self):
		from upande_livestock.serverscripts.alerts import tasks

		switch(PD, False)
		event_types.disabled_events()  # read the switch before the query is stood in for
		with patch.object(tasks.frappe.db, "sql", side_effect=AssertionError("queried")):
			self.assertEqual(tasks.pregnancy_checks_due(), {})

	def test_the_sweep_leaves_out_alerts_for_a_disabled_event(self):
		from upande_livestock.serverscripts.alerts import raise_alerts as RA

		if not frappe.db.exists(EVENT_TYPE, "Calving"):
			self.skipTest("no Calving event type")
		calving = {"kind": "Calving Due", "animal": "A1", "severity": "Due", "message": "m", "detail": {}}
		open_cow = {"kind": "Cow Open Too Long", "animal": "A2", "severity": "Overdue", "message": "m", "detail": {}}
		with patch.object(RA.herd_movement, "suggestions", return_value={"growth": [], "open_cows": []}), \
			patch.object(RA, "calving_due", return_value=[calving]), \
			patch.object(RA, "weight_alerts", return_value=[open_cow]), \
			patch.object(RA, "calf_separation_alerts", return_value=[]), \
			patch.object(RA, "inbreeding_alerts", return_value=[]), \
			patch.object(RA, "concentrate_alerts", return_value=[]):
			switch("Calving", True)
			self.assertEqual({a["kind"] for a in RA.collect()}, {"Calving Due", "Cow Open Too Long"})
			switch("Calving", False)
			self.assertEqual({a["kind"] for a in RA.collect()}, {"Cow Open Too Long"})

	def test_open_alerts_hide_a_disabled_events_alert(self):
		from upande_livestock.serverscripts.alerts.open_alerts import open_alerts

		rows = [frappe._dict(name="1", alert_kind="Pregnancy Check Overdue"),
		        frappe._dict(name="2", alert_kind="Cow Open Too Long")]
		switch(PD, False)
		event_types.disabled_events()  # read the switch before get_all is stood in for
		with patch("frappe.get_all", return_value=rows):
			res = open_alerts()
		self.assertEqual([r.alert_kind for r in res["alerts"]], ["Cow Open Too Long"])

	def test_the_breeding_list_has_no_pregnancy_checks_with_pd_off(self):
		from upande_livestock.serverscripts.breeding.breeding_lists import breeding_lists

		switch(PD, False)
		res = breeding_lists()
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(res["pregnancy_checks"], [])


class TestThePhoneIsTold(EventSwitchCase):
	def test_the_bootstrap_names_the_disabled_events(self):
		from upande_livestock.serverscripts.mobile.get_bootstrap_bundle import get_bootstrap_bundle

		switch(PD, False)
		res = get_bootstrap_bundle()
		self.assertNotIn("error", res, res.get("error"))
		self.assertIn(PD, res["disabled_events"])
		self.assertNotIn(PD, [t["name"] for t in res["event_types"]])
		switch(PD, True)
		res = get_bootstrap_bundle()
		self.assertNotIn(PD, res["disabled_events"])


class TestTheRetroPathDropsItsDiagnosis(EventSwitchCase):
	def test_pd_off_beats_the_back_recording_setting(self):
		with patch.object(birth_window.frappe.db, "get_single_value", return_value=1):
			switch(PD, True)
			self.assertTrue(birth_window.allows_diagnosis())
			switch(PD, False)
			self.assertFalse(birth_window.allows_diagnosis())


class TestTheSettingsScreen(EventSwitchCase):
	def test_a_disabled_type_is_still_listed_with_its_timings(self):
		from upande_livestock.serverscripts.settings.stock_rules import stock_rules

		switch(PD, False)
		res = stock_rules()
		row = next(r for r in res["rules"] if r["event_type"] == PD)
		self.assertFalse(row["enabled"])
		self.assertIn("pregnancy_check_days_after_service", row["timings"])

	def test_switching_off_keeps_the_stock_rule(self):
		from upande_livestock.serverscripts.settings.save_stock_rules import save_stock_rules

		group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		if not group:
			self.skipTest("no leaf item group")
		switch(PD, True)
		rule = {"event_type": PD, "posts_stock_entry": True, "item_groups": [group]}
		self.assertNotIn("error", save_stock_rules({"rules": [rule]}))
		res = save_stock_rules({"rules": [dict(rule, enabled=False)]})
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(res["changed"], [PD])
		doc = frappe.get_doc(EVENT_TYPE, PD)
		self.assertEqual((doc.is_active, doc.posts_stock_entry), (0, 1))
		self.assertEqual([r.item_group for r in doc.stock_item_groups], [group])
		self.assertFalse(event_types.is_enabled(PD))

	def test_a_rule_without_enabled_leaves_the_switch(self):
		from upande_livestock.serverscripts.settings.save_stock_rules import save_stock_rules

		switch(PD, False)
		save_stock_rules({"rules": [{"event_type": PD, "posts_stock_entry": False}]})
		self.assertEqual(frappe.db.get_value(EVENT_TYPE, PD, "is_active"), 0)

	def test_husbandry_offers_only_enabled_types(self):
		from upande_livestock.serverscripts.husbandry.husbandry_options import husbandry_options

		if not frappe.db.exists(EVENT_TYPE, "Dehorning"):
			self.skipTest("no Dehorning event type")
		switch("Dehorning", False)
		res = husbandry_options()
		self.assertNotIn("error", res, res.get("error"))
		self.assertNotIn("Dehorning", res["event_types"])


class TestThePatchSwitchesEveryTypeOn(EventSwitchCase):
	def test_every_existing_type_starts_on(self):
		from upande_livestock.patches import enable_every_event_type

		switch(PD, False)
		# reload_doc can commit; the doctype is already current here.
		with patch.object(frappe, "reload_doc"):
			enable_every_event_type.execute()
		event_types.forget()
		self.assertEqual(frappe.db.get_value(EVENT_TYPE, PD, "is_active"), 1)
		self.assertEqual(frappe.db.count(EVENT_TYPE, {"is_active": 0}), 0)
