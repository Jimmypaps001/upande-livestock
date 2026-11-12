# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""An event type the farm switched off (Settings -> Events).

Switched off, an event is refused by the server when someone records a new one
unless the write is plumbing for another event; raises no alert and fills no
worklist that would prompt for it; is named in the phone's bootstrap; and is
still listed on the Settings screen so it can be switched back on.

The exemptions matter as much as the refusal: a calving moves its dam and
registers its calves, a Health Case writes its timeline mirror, a cull review
mark writes its history note, whatever is switched off. Those writes carry
`flags.ignore_event_enabled`.

These tests switch types off and commit nothing of their own, but the fixtures
they build (see test_calving_routing) commit when purged, so every switch is put
back explicitly.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import event_types
from upande_livestock.serverscripts.tests.test_operations import (
	_make_cow,
	_open_backdating_window,
	_purge,
	_purge_events_for,
)

EVENT_TYPE = "Livestock Event Type"
PD = "Pregnancy Diagnosis"


def _employee():
	return frappe.db.get_value("Employee", {"status": "Active"}, "name")


def switch(name, on):
	frappe.db.set_value(EVENT_TYPE, name, "is_active", 1 if on else 0)
	event_types.forget()


class EventSwitchCase(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists(EVENT_TYPE, PD):
			self.skipTest("no Pregnancy Diagnosis event type on this site")
		# Whatever a test switches, put it back and commit (other fixtures commit).
		self._was = {r.name: r.is_active for r in frappe.get_all(EVENT_TYPE, fields=["name", "is_active"])}
		self.addCleanup(self._restore)
		event_types.forget()

	def _restore(self):
		for name, on in self._was.items():
			frappe.db.set_value(EVENT_TYPE, name, "is_active", on)
		event_types.forget()
		frappe.db.commit()


class TestTheServerRefusesADisabledEvent(EventSwitchCase):
	def _new(self, **flags):
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = PD
		doc.event_date = today()
		for k, v in flags.items():
			doc.flags[k] = v
		return doc

	def test_a_new_event_of_a_disabled_type_is_refused_in_words(self):
		switch(PD, False)
		with self.assertRaises(frappe.ValidationError) as caught:
			self._new().insert(ignore_permissions=True)
		self.assertIn("switched off", str(caught.exception))
		self.assertIn("Settings", str(caught.exception))

	def test_an_enabled_type_is_not_refused_for_it(self):
		switch(PD, True)
		with self.assertRaises(Exception) as caught:
			# Refused for something else (no animal, no operator) - not the switch.
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
	def test_every_event_alert_kind_follows_its_event(self):
		for kind, event in (
			("Pregnancy Check Overdue", PD), ("Calving Due", "Calving"),
			("Move Due", "Movement"), ("Move Overdue", "Movement"),
		):
			switch(event, False)
			self.assertFalse(event_types.alert_wanted(kind), kind)
			switch(event, True)
			self.assertTrue(event_types.alert_wanted(kind), kind)

	def test_the_mapped_alert_kinds_are_real_kinds_and_event_types(self):
		from upande_livestock.serverscripts.alerts._shared import KINDS

		for kind, event in event_types.ALERT_EVENT.items():
			if kind != "Weighing Overdue":  # kept for a farm that raises it; Kaitet has no such alert
				self.assertIn(kind, KINDS)
			self.assertTrue(frappe.db.exists(EVENT_TYPE, event), event)

	def test_alerts_about_the_animal_stay(self):
		switch(PD, False)
		for kind in ("Cow Open Too Long", "Bull Cull Due", "Concentrate Low"):
			self.assertTrue(event_types.alert_wanted(kind), kind)

	def test_no_pregnancy_check_is_owed_with_pd_off(self):
		from upande_livestock.serverscripts.alerts import tasks

		switch(PD, False)
		event_types.disabled_events()  # read the switch before the query is stood in for
		with patch.object(tasks.frappe.db, "sql", side_effect=AssertionError("queried")):
			self.assertEqual(tasks.pregnancy_checks_due(), {})

	def test_the_sweep_leaves_out_alerts_for_a_disabled_event(self):
		from upande_livestock.serverscripts.alerts import raise_alerts as RA

		calving = {"kind": "Calving Due", "animal": "A1", "severity": "Due", "message": "m", "detail": {}}
		with patch.object(RA.herd_movement, "suggestions",
		                  return_value={"bulls": [], "growth": [], "open_cows": [{
			"animal": "A2", "label": "A2", "herd": "H", "open_days": 400, "limit": 300, "days_over": 100}]}), \
			patch.object(RA, "calving_due", return_value=[calving]), \
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

	def test_delivery_skips_an_alert_still_open_for_a_disabled_event(self):
		from upande_livestock.serverscripts.common import notifications

		rows = [frappe._dict(name="1", alert_kind="Pregnancy Check Overdue", herd=None)]
		switch(PD, False)
		event_types.disabled_events()
		with patch.object(notifications.frappe, "get_all", return_value=rows):
			self.assertEqual(notifications.deliver_open_alerts(), {"alerts": 0, "delivered": 0, "skipped": 0})

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

	def test_the_web_page_carries_them_too(self):
		from upande_livestock.www import livestock_app

		switch(PD, False)
		ctx = frappe._dict()
		try:
			livestock_app.get_context(ctx)
		except Exception as e:  # not logged in / no build: only the bootstrap matters
			self.skipTest("page not renderable here: {}".format(e))
		self.assertIn(PD, frappe.parse_json(ctx.bootstrap_json)["disabled_events"])


class TestTheSettingsScreen(EventSwitchCase):
	def test_a_disabled_type_is_still_listed_with_its_timings(self):
		from upande_livestock.serverscripts.settings.stock_rules import stock_rules

		switch(PD, False)
		res = stock_rules()
		self.assertNotIn("error", res, res.get("error"))
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
		with patch.object(frappe, "reload_doc"):
			enable_every_event_type.execute()
		event_types.forget()
		self.assertEqual(frappe.db.get_value(EVENT_TYPE, PD, "is_active"), 1)
		self.assertEqual(frappe.db.count(EVENT_TYPE, {"is_active": 0}), 0)


class TestFeedIsNotIssuedWithFeedingOff(EventSwitchCase):
	"""Every way of giving a herd feed is a Feeding event. With Feeding off the
	endpoint refuses in the switch's own words before any stock moves."""

	def _refused(self, reply):
		self.assertIsInstance(reply, dict)
		self.assertIn("switched off", reply.get("error") or "")
		self.assertIn("Settings", reply["error"])

	def test_each_feed_issuing_endpoint_refuses(self):
		from upande_livestock.serverscripts.feeding.issue_feed import issue_feed
		from upande_livestock.serverscripts.feeding.manual_feed import manual_feed
		from upande_livestock.serverscripts.feeding.manufacture_feed import manufacture_feed
		from upande_livestock.serverscripts.mobile.record_feeding import record_feeding

		switch("Feeding", False)
		self._refused(manufacture_feed("No Such Herd"))
		self._refused(manual_feed({"herd": "No Such Herd"}))
		self._refused(issue_feed("No Such Herd", 10))
		for action in ("manufacture", "issue", "manual"):
			self._refused(record_feeding({"action": action, "herd": "No Such Herd"}))

	def test_feeding_on_is_not_refused_for_it(self):
		from upande_livestock.serverscripts.feeding.issue_feed import issue_feed

		switch("Feeding", True)
		reply = issue_feed("No Such Herd", 10)
		self.assertNotIn("switched off", (reply or {}).get("error") or "")


class TestMovementOffStillLetsInternalMovesThrough(EventSwitchCase):
	def test_a_movement_the_operator_records_is_refused(self):
		switch("Movement", False)
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Movement"
		doc.event_date = today()
		with self.assertRaises(frappe.ValidationError) as caught:
			doc.insert(ignore_permissions=True)
		self.assertIn("Movement is switched off", str(caught.exception))


class TestACalvingIsNotUndoneByMovementOrBirthOff(EventSwitchCase):
	"""The dam's move after calving and each calf's Birth event are plumbing of the
	Calving. A farm that switched Movement and Birth off still calves its cows."""

	def setUp(self):
		super().setUp()
		_open_backdating_window(self)
		from upande_livestock.serverscripts.common import herd_movement as hm

		self.employee = _employee()
		self.destination = hm.post_calving_herd()
		if not (self.employee and self.destination and frappe.db.exists("Herds", "STEAMERS")):
			raise unittest.SkipTest("no employee / post-calving herd / STEAMERS here")
		self.dam = _make_cow("ZZ SWITCH DAM", months_old=48, herd="STEAMERS")
		self.addCleanup(_purge_events_for, self.dam.name)
		self.addCleanup(_purge, "Animal", self.dam.name)

		from upande_livestock.serverscripts.breeding.create_service_event import create_service_event

		served = add_days(today(), -285)
		r = create_service_event({
			"animal": self.dam.name, "service_type": "A.I.",
			"service_date": served, "operator": self.employee,
		})
		if r.get("error"):
			raise unittest.SkipTest("could not record a service: {}".format(r["error"][:120]))
		dx = frappe.new_doc("Livestock Event")
		dx.event_type = PD
		dx.animal = self.dam.name
		dx.event_date = add_days(served, 60)
		dx.operator = self.employee
		dx.diagnosis_result = "Confirmed"
		dx.related_service = r["name"]
		dx.insert(ignore_permissions=True)
		dx.submit()

	def test_the_dam_is_moved_and_the_calf_registered_with_movement_and_birth_off(self):
		from upande_livestock.serverscripts.breeding.record_birth import record_birth

		switch("Movement", False)
		switch("Birth", False)
		res = record_birth({
			"dam": self.dam.name, "operator": self.employee, "event_date": today(),
			"outcome": "Live Birth",
			"calves": [{"tag": "ZZ SWITCH CALF", "sex": "Female", "birth_weight": 30}],
		})
		self.assertFalse(res.get("error"), res.get("error"))
		calf = res["calves"][0]["animal"]
		self.addCleanup(_purge, "Animal", calf)
		self.addCleanup(_purge_events_for, calf)
		for name in frappe.get_all("Livestock Event", filters={"dam": self.dam.name}, pluck="name"):
			self.addCleanup(_purge, "Livestock Event", name)
		self.assertEqual(
			frappe.db.get_value("Animal", self.dam.name, "current_herd"), self.destination)
		self.assertTrue(frappe.db.exists("Animal", calf), res)
		self.assertTrue(frappe.db.exists("Livestock Event", {"dam": self.dam.name, "event_type": "Birth"}), res)

	def test_a_calving_itself_is_refused_with_calving_off(self):
		from upande_livestock.serverscripts.breeding.record_birth import record_birth

		switch("Calving", False)
		res = record_birth({
			"dam": self.dam.name, "operator": self.employee, "event_date": today(),
			"outcome": "Live Birth",
			"calves": [{"tag": "ZZ SWITCH CALF", "sex": "Female", "birth_weight": 30}],
		})
		self.assertIn("switched off", res.get("error") or "")


class TestTheMirrorAndCullReviewWritesAreExempt(EventSwitchCase):
	def test_a_health_case_still_reaches_the_timeline_with_its_type_off(self):
		tag = "ZZ SWITCH MIRROR"
		self.addCleanup(_purge_events_for, tag)
		self.addCleanup(_purge, "Animal", tag)
		cow = _make_cow(tag)
		switch("Health Case", False)
		hc = frappe.get_doc({
			"doctype": "Livestock Health Case", "animal": cow.name, "opened_date": today(),
			"case_status": "Open", "presenting_symptoms": "Off feed",
		}).insert(ignore_permissions=True)
		self.addCleanup(lambda: (frappe.db.delete("Livestock Health Case", {"name": hc.name}), frappe.db.commit()))
		hc.submit()
		events = frappe.get_all(
			"Livestock Event", filters={"reference_doctype": "Livestock Health Case", "reference_name": hc.name})
		self.assertEqual(len(events), 1)

	def test_a_cull_review_mark_still_writes_its_history_with_the_type_off(self):
		from upande_livestock.serverscripts.animals.mark_cull_review import EVENT_TYPE as CULL, mark_cull_review

		tag = "ZZ SWITCH CULL"
		self.addCleanup(_purge_events_for, tag)
		self.addCleanup(_purge, "Animal", tag)
		cow = _make_cow(tag)
		if not frappe.db.exists(EVENT_TYPE, CULL):
			self.skipTest("no cull review event type")
		switch(CULL, False)
		got = mark_cull_review({"animal": cow.name, "reason": "worth a look", "operator": _employee()})
		self.assertFalse(got.get("error"), got.get("error"))
		self.assertTrue(frappe.db.exists("Livestock Event", {"animal": cow.name, "event_type": CULL}))
