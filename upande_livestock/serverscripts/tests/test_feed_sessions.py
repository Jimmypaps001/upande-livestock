# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A herd's feed day mixed in two sessions (half day / full day).

The engine is stubbed (it has its own tests): what is checked here is the share
of the day each session asks it to mix, the state machine, the over-feed guard,
the second-session alert and its reminder, and the per-animal intake.

    bench --site kaitet.local run-tests --app upande_livestock \
        --module upande_livestock.serverscripts.tests.test_feed_sessions
"""

import datetime
import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.feeding import _engine as feeding
from upande_livestock.serverscripts.feeding import _sessions as S
from upande_livestock.serverscripts.feeding import feed_actuals as FA
from upande_livestock.serverscripts.feeding import manufacture_feed as MF


class TestSessionRules(unittest.TestCase):
	def test_the_choice_is_read_from_whatever_a_screen_sends(self):
		for given, want in [(None, "Full"), ("Full day", "Full"), ("full", "Full"), ("Half", "Half"),
		                    ("Half day", "Half"), ("half_1", "Half-1"), ("Half-2", "Half-2")]:
			self.assertEqual(S.normalise(given), want)
		with self.assertRaises(frappe.ValidationError):
			S.normalise("a third")

	def test_state_from_the_share_fed(self):
		self.assertEqual(S.state_of(0), "not_fed")
		self.assertEqual(S.state_of(0.5), "half_fed")
		self.assertEqual(S.state_of(1.0), "fully_fed")
		self.assertEqual(S.state_of(1.5), "fully_fed")

	def test_a_reminder_is_due_after_the_time_and_only_once(self):
		at = datetime.time(14, 0)
		self.assertFalse(S.reminder_due(datetime.time(13, 59), at, {}))
		self.assertTrue(S.reminder_due(datetime.time(14, 0), at, {}))
		self.assertTrue(S.reminder_due(datetime.time(18, 30), at, None))
		self.assertFalse(S.reminder_due(datetime.time(18, 30), at, {"reminded": True}))


def _fake_engine(captured):
	def fake(herd, **kw):
		captured.append(kw)
		heads = kw.get("heads") or feeding._herd_bom(herd)[2]
		bom = kw.get("bom_no") or frappe.db.get_value("Herds", herd, "bom")
		qty = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1.0
		total = flt(kw["typed_total"]) if kw.get("typed_total") else flt(qty * heads * kw.get("portion", 1.0), 3)
		return {"work_order": None, "transfer_stock_entry": None, "manufacture_stock_entry": None,
		        "issue_stock_entry": "", "livestock_event": None, "heads": heads, "bom_no": bom,
		        "produced_qty": total, "portion": kw.get("portion", 1.0)}

	return fake


class TestFeedSessions(IntegrationTestCase):
	def setUp(self):
		self.herd = None
		for h in frappe.get_all("Herds", filters=[["bom", "is", "set"]], pluck="name", order_by="name asc"):
			try:
				heads = feeding._herd_bom(h)[2]
			except frappe.ValidationError:
				continue
			if heads > 0 and not FA._fed_fraction(h, today()) and not FA._record_name(h, today()):
				self.herd, self.heads = h, heads
				break
		if not self.herd:
			raise unittest.SkipTest("no herd with a recipe, animals and an unfed today")
		self.calls, self.sent = [], []
		for patcher in (
			patch.object(feeding, "manufacture_herd_feed", side_effect=_fake_engine(self.calls)),
			patch("upande_livestock.serverscripts.common.notifications.notify",
			      side_effect=lambda users, subject, *a, **k: self.sent.append(subject) or list(users)),
			patch("upande_livestock.serverscripts.common.notifications.audience_for_alert", return_value=["Administrator"]),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		self.addCleanup(self._clean)
		self.addCleanup(frappe.set_user, "Administrator")

	def _clean(self):
		frappe.set_user("Administrator")
		for n in frappe.get_all(S.DT, filters={"herd": self.herd, "date": today()}, pluck="name"):
			frappe.delete_doc(S.DT, n, force=True, ignore_permissions=True)
		for n in frappe.get_all("Livestock Alert", filters={"alert_kind": S.ALERT_KIND, "herd": self.herd}, pluck="name"):
			frappe.delete_doc("Livestock Alert", n, force=True, ignore_permissions=True)
		name = FA._record_name(self.herd, today())
		if name:
			frappe.delete_doc(FA.DOCTYPE, name, force=True, ignore_permissions=True)

	def _mix(self, session=None, **kw):
		return FA.manufacture_day(self.herd, today(), employee=None, feed_session=session, **kw)

	def test_a_half_day_mixes_half_the_plan_and_the_second_half_the_rest(self):
		first = self._mix("Half")
		self.assertEqual(self.calls[-1]["portion"], 0.5)
		self.assertEqual(first["day_state"], "half_fed")
		self.assertEqual(first["status"], "Half fed")
		self.assertEqual(first["session"]["label"], "Half fed (1 of 2)")
		self.assertTrue(first["session"]["second_due"])
		self.assertEqual(first["session"]["sessions"][0]["feed_session"], "Half-1")
		self.assertAlmostEqual(first["fed_kg"], first["planned_kg"] / 2, places=2)
		second = self._mix("Half")
		self.assertEqual(second["session"]["sessions"][1]["feed_session"], "Half-2")
		self.assertEqual(second["day_state"], "fully_fed")
		self.assertEqual(second["status"], "Manufactured")
		self.assertAlmostEqual(second["fed_kg"], second["planned_kg"], places=2)
		self.assertEqual(frappe.db.get_value(FA.DOCTYPE, second["record"], "fed_fraction"), 1)

	def test_a_full_day_is_one_session(self):
		out = self._mix("Full")
		self.assertEqual(self.calls[-1]["portion"], 1.0)
		self.assertEqual(out["day_state"], "fully_fed")
		self.assertEqual(out["session"]["sessions"][0]["feed_session"], "Full")

	def test_a_half_of_an_amended_day_is_half_of_what_was_amended(self):
		item = self._amend(plus=100)
		out = self._mix("Half-1")
		self.assertAlmostEqual(self.calls[-1]["typed_total"], out["actual_kg"] / 2, places=2)
		sess = out["session"]["sessions"][0]
		self.assertTrue(sess["amended"])
		comp = next(c for c in sess["components"] if c["item_code"] == item["item_code"])
		self.assertAlmostEqual(comp["fed_kg"], (item["planned_kg"] + 100) / 2, places=2)
		self.assertAlmostEqual(comp["planned_kg"], item["planned_kg"] / 2, places=2)

	def _amend(self, plus):
		item = FA.herd_day(self.herd, today())["components"][0]
		FA.amend_day(self.herd, today(), [{"item_code": item["item_code"], "actual_kg": item["planned_kg"] + plus}])
		return item

	def test_more_than_a_day_needs_a_manager(self):
		self._mix("Half")
		# a full day after a half, and a third session after two, are refused
		with self.assertRaises(frappe.ValidationError):
			self._mix("Full")
		self._mix("Half")
		with self.assertRaises(frappe.ValidationError):
			self._mix("Half")
		with self.assertRaises(frappe.ValidationError):
			self._mix("Half-2")
		self.assertEqual(len(S.sessions_of(self.herd, today())), 2)
		# the manager's override feeds it, and the session says so
		with patch.object(S, "can_override", return_value=False), self.assertRaises(frappe.ValidationError):
			self._mix("Half", override=True)
		out = self._mix("Half", override=True)
		self.assertTrue(out["session"]["sessions"][-1]["overridden"])
		self.assertEqual(out["session"]["label"], "Over-fed (1.5 days)")

	def test_the_same_half_twice_is_refused(self):
		self._mix("Half-1")
		with self.assertRaises(frappe.ValidationError):
			self._mix("Half-1")

	def test_a_day_fed_in_half_can_still_be_amended_but_not_reset(self):
		self._mix("Half")
		self._amend(plus=10)
		self.assertEqual(frappe.db.get_value(FA.DOCTYPE, FA._record_name(self.herd, today()), "status"), "Half fed")
		with self.assertRaises(frappe.ValidationError):
			FA.reset_day(self.herd, today())

	def test_a_cancelled_session_no_longer_counts(self):
		self._mix("Half")
		name = S.sessions_of(self.herd, today())[0]["name"]
		frappe.db.set_value(S.DT, name, "status", "Cancelled")
		self.assertEqual(FA._fed_fraction(self.herd, today()), 0)
		self.assertEqual(S.session_state(self.herd, today())["state"], "not_fed")
		# and the day can be fed again from the start
		self.assertEqual(self._mix("Half")["session"]["sessions"][0]["feed_session"], "Half-1")

	def test_intake_compares_what_was_fed_with_the_half_that_was_planned(self):
		self._mix("Half")
		intake = FA.per_animal_intake(self.herd, today())
		day = FA.herd_day(self.herd, today())
		self.assertAlmostEqual(intake["actual_kg"], day["planned_per_head"] / 2, places=2)
		self.assertAlmostEqual(intake["planned_kg"], day["planned_per_head"] / 2, places=2)
		self.assertEqual(intake["appetite"], "on_plan")

	def test_the_report_shows_sessions_and_what_was_fed_so_far(self):
		from upande_livestock.serverscripts.feeding import daily_feed_report as report

		self._mix("Half")
		out = report.get_daily_feed_report(today(), self.herd)
		row = out["herds"][0]
		self.assertEqual(row["day_state"], "half_fed")
		self.assertEqual(row["fed_fraction"], 0.5)
		self.assertEqual([s["feed_session"] for s in row["sessions"]], ["Half-1"])
		self.assertAlmostEqual(row["actual_kg"], row["planned_kg"], places=2)  # the half that was planned

	def test_a_system_run_asks_the_same_question(self):
		res = MF.manufacture_feed(self.herd, feed_session="Half")
		self.assertTrue(res["ok"], res)
		self.assertEqual(self.calls[-1]["portion"], 0.5)
		self.assertEqual(res["session"]["state"], "half_fed")
		self.assertEqual(S.sessions_of(self.herd, today())[0]["source"], "System")
		res = MF.manufacture_feed(self.herd, feed_session="Half")
		self.assertEqual(res["session"]["state"], "fully_fed")
		self.assertIn("error", MF.manufacture_feed(self.herd, feed_session="Full"))

	def test_an_old_caller_with_only_a_portion_is_read_as_a_half(self):
		res = MF.manufacture_feed(self.herd, portion=0.5)
		self.assertEqual(res["session"]["next_session"], "Half-2")

	def test_the_herdsman_is_told_at_once_and_it_settles_with_the_second_session(self):
		self._mix("Half")
		alerts = frappe.get_all("Livestock Alert", filters={"alert_kind": S.ALERT_KIND, "herd": self.herd},
		                        fields=["status", "alert_date"])
		self.assertEqual([(a.status, str(a.alert_date)) for a in alerts], [("Open", today())])
		self.assertEqual(len(self.sent), 1)
		self.assertIn("second session", self.sent[0])
		self._mix("Half")
		self.assertEqual(frappe.db.get_value("Livestock Alert", {"alert_kind": S.ALERT_KIND, "herd": self.herd}, "status"),
		                 "Actioned")

	def test_a_full_day_raises_nothing(self):
		self._mix("Full")
		self.assertFalse(frappe.db.exists("Livestock Alert", {"alert_kind": S.ALERT_KIND, "herd": self.herd}))
		self.assertEqual(self.sent, [])

	def test_the_reminder_goes_once_after_the_set_time(self):
		self._mix("Half")
		self.sent.clear()
		with patch.object(S, "reminder_time", return_value=datetime.time(14, 0)):
			early = datetime.datetime.combine(datetime.date.today(), datetime.time(9, 0))
			late = datetime.datetime.combine(datetime.date.today(), datetime.time(15, 0))
			self.assertNotIn(self.herd, S.send_reminders(early))
			self.assertEqual(self.sent, [])
			self.assertIn(self.herd, S.send_reminders(late))
			self.assertEqual(len(self.sent), 1)
			self.assertIn("Reminder", self.sent[0])
			self.assertNotIn(self.herd, S.send_reminders(late))
			self.assertEqual(len(self.sent), 1)

	def test_no_reminder_when_the_second_session_has_happened_and_yesterdays_alert_closes(self):
		self._mix("Half")
		self._mix("Half")
		self.sent.clear()
		alert = S.raise_second_due(self.herd, today())  # a stale open alert for a day that is now complete
		self.sent.clear()
		late = datetime.datetime.combine(datetime.date.today(), datetime.time(23, 0))
		S.send_reminders(late)
		self.assertEqual(self.sent, [])
		self.assertEqual(frappe.db.get_value("Livestock Alert", alert, "status"), "Actioned")
		old = S.raise_second_due(self.herd, add_days(today(), -1))
		S.send_reminders(late)
		self.assertEqual(frappe.db.get_value("Livestock Alert", old, "status"), "Dismissed")

	def test_the_stock_entries_carry_the_session(self):
		with patch.object(S.frappe.db, "set_value", wraps=frappe.db.set_value) as sv:
			S.stamp_documents({"work_order": "WO-1", "transfer_stock_entry": "SE-1"}, "Half-1", 0.5)
		touched = {c.args[0] for c in sv.call_args_list}
		self.assertTrue(touched <= {"Work Order", "Stock Entry"})
