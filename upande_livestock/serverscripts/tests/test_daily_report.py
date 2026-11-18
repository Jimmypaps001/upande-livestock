# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The daily report email: who gets it, when it goes, what it counts."""

import datetime

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.reports import daily_report as dr
from upande_livestock.serverscripts.settings import daily_report as settings_api
from upande_livestock.serverscripts.tests.beef_fixtures import (
	isolate,
	make_animal,
	make_herd,
	move_animal,
	submit_weight,
)

SETTINGS = "Livestock Settings"


def make_user(email, enabled=1, roles=(), profile=None):
	u = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": email.split("@")[0], "enabled": enabled,
		 "send_welcome_email": 0, "user_type": "System User"}
	)
	u.insert(ignore_permissions=True)
	for r in roles:
		u.append("roles", {"role": r})
	if profile:
		u.append("role_profiles", {"role_profile": profile})
	u.save(ignore_permissions=True)
	frappe.db.set_value("User", u.name, "enabled", enabled)
	return u.name


def save_lists(roles=(), profiles=()):
	frappe.set_user("Administrator")
	settings_api.save_daily_report_settings({"roles": list(roles), "role_profiles": list(profiles)})


class TestDailyReport(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		frappe.set_user("Administrator")
		for f, v in (("daily_report_enabled", 0), ("daily_report_head", None),
		             ("daily_report_time", "18:00:00")):
			frappe.db.set_single_value(SETTINGS, f, v)
		frappe.db.set_default(dr.LAST_SENT_KEY, "")
		save_lists()

	# -- recipients ---------------------------------------------------------

	def test_recipients_head_roles_profiles_dedupe_and_disabled(self):
		if not frappe.db.exists("Role Profile", "ZZ Report Profile"):
			frappe.get_doc({"doctype": "Role Profile", "role_profile": "ZZ Report Profile",
			                "roles": [{"role": "Livestock Attendant"}]}).insert(ignore_permissions=True)
		head = make_user("zz_head@example.com")
		by_role = make_user("zz_role@example.com", roles=["Livestock Vet"])
		by_profile = make_user("zz_prof@example.com", profile="ZZ Report Profile")
		both = make_user("zz_both@example.com", roles=["Livestock Vet"], profile="ZZ Report Profile")
		disabled = make_user("zz_off@example.com", enabled=0, roles=["Livestock Vet"])
		other = make_user("zz_other@example.com", roles=["Livestock Stores"])
		frappe.db.set_single_value(SETTINGS, "daily_report_head", head)
		save_lists(["Livestock Vet"], ["ZZ Report Profile"])

		got = {r["user"] for r in dr.recipients()}
		self.assertTrue({head, by_role, by_profile, both} <= got)
		self.assertNotIn(disabled, got)
		self.assertNotIn(other, got)
		emails = [r["email"] for r in dr.recipients()]
		self.assertEqual(len(emails), len(set(emails)))
		self.assertEqual(sum(1 for r in dr.recipients() if r["user"] == both), 1)

	def test_user_without_email_is_skipped(self):
		u = make_user("zz_noemail@example.com", roles=["Livestock Vet"])
		frappe.db.set_value("User", u, "email", "")
		save_lists(["Livestock Vet"])
		self.assertNotIn(u, {r["user"] for r in dr.recipients()})

	def test_no_choices_no_recipients(self):
		self.assertEqual(dr.recipients(), [])

	# -- the clock ----------------------------------------------------------

	def at(self, hh, mm=0, day=None):
		d = frappe.utils.getdate(day or today())
		return datetime.datetime.combine(d, datetime.time(hh, mm))

	def test_time_gate(self):
		frappe.db.set_single_value(SETTINGS, "daily_report_enabled", 1)
		self.assertFalse(dr.is_due(now=self.at(17, 59)))
		self.assertTrue(dr.is_due(now=self.at(18, 0)))
		self.assertTrue(dr.is_due(now=self.at(23, 45)))

	def test_disabled_never_due(self):
		self.assertFalse(dr.is_due(now=self.at(20)))

	def test_sends_once_per_day(self):
		from unittest.mock import patch

		head = make_user("zz_once@example.com")
		frappe.db.set_single_value(SETTINGS, "daily_report_head", head)
		frappe.db.set_single_value(SETTINGS, "daily_report_enabled", 1)
		with patch("frappe.sendmail") as mail:
			self.assertTrue(dr.send_due(now=self.at(18, 15)))
			self.assertFalse(dr.send_due(now=self.at(18, 30)))
			self.assertFalse(dr.is_due(now=self.at(23, 0)))
			self.assertEqual(mail.call_count, 1)
			self.assertEqual(mail.call_args.kwargs["recipients"], [head])
			self.assertIn("Livestock daily report", mail.call_args.kwargs["message"])
			# the next day it is due again
			self.assertTrue(dr.is_due(now=self.at(18, 5, add_days(today(), 1))))

	def test_failed_send_hands_the_day_back(self):
		from unittest.mock import patch

		head = make_user("zz_fail@example.com")
		frappe.db.set_single_value(SETTINGS, "daily_report_head", head)
		frappe.db.set_single_value(SETTINGS, "daily_report_enabled", 1)
		with patch("frappe.sendmail", side_effect=frappe.OutgoingEmailError("no account")):
			self.assertFalse(dr.send_due(now=self.at(19)))
		self.assertTrue(dr.is_due(now=self.at(19)))

	def test_nobody_to_send_to_keeps_the_day_open(self):
		frappe.db.set_single_value(SETTINGS, "daily_report_enabled", 1)
		self.assertFalse(dr.send_due(now=self.at(19)))
		self.assertTrue(dr.is_due(now=self.at(19)))

	# -- content ------------------------------------------------------------

	def test_counts_on_fixture_data(self):
		a, b = make_herd("ZZ Rep A"), make_herd("ZZ Rep B")
		cow1, cow2 = make_animal(a.name), make_animal(a.name)
		submit_weight(cow1.name, 300)
		submit_weight(cow2.name, 400)
		move_animal(cow1.name, b.name)

		ctx = dr.build_context(today())
		self.assertEqual(ctx["weighings"]["animals"], 2)
		self.assertEqual(ctx["weighings"]["average_kg"], 350)
		self.assertEqual(ctx["movements"]["count"], 1)
		self.assertEqual(ctx["movements"]["rows"][0]["to_herd"], b.name)
		kinds = {r.event_type: r.n for r in ctx["activities"]["rows"]}
		self.assertEqual(kinds.get("Movement"), 1)

		# nothing happened yesterday
		quiet = dr.build_context(add_days(today(), -30))
		self.assertEqual(quiet["activities"]["total"], 0)

	def test_gallagher_sessions_listed(self):
		herd = make_herd("ZZ Rep G")
		cow = make_animal(herd.name)
		rec = submit_weight(cow.name, 250)
		frappe.db.set_value("Livestock Weight Record", rec.name, "remarks",
		                    "Gallagher scale file crush1.csv, row 2.")
		w = dr.weighings(today())
		self.assertEqual(w["gallagher"], [{"file": "crush1.csv", "animals": 1}])

	def test_health_counts_and_sick_list(self):
		herd = make_herd("ZZ Rep H")
		cow = make_animal(herd.name)
		case = frappe.get_doc({"doctype": "Livestock Health Case", "animal": cow.name,
		                       "opened_date": today(), "case_status": "Open",
		                       "presenting_symptoms": "limp"})
		case.insert(ignore_permissions=True)
		h = dr.health(today())
		self.assertGreaterEqual(h["new_cases"], 1)
		self.assertTrue(any(s["case"] == case.name and s["tag"] == cow.tag_number for s in h["sick"]))
		self.assertEqual(h["open_cases"], len(h["sick"]))

	def test_feeding_section_degrades_without_the_report(self):
		from unittest.mock import patch

		with patch.dict("sys.modules", {"upande_livestock.serverscripts.feeding.daily_feed_report": None}):
			self.assertEqual(dr.feeding(today()), {"available": False})

	def test_feeding_section_summarises_the_report(self):
		from unittest.mock import patch

		fake = {"herds": [{"herd": "H", "herd_name": "H", "head_count": 3, "planned_kg": 30, "actual_kg": 28, "amended": 0}],
		        "animals": [{"animal": "A", "tag": "T1", "herd": "H", "planned_kg": 10, "actual_kg": 7,
		                     "variance_pct": -30, "appetite": "below"},
		                    {"animal": "C", "tag": "T3", "herd": "H", "planned_kg": 10, "actual_kg": 10.2,
		                     "variance_pct": 2, "appetite": "above"},
		                    {"animal": "D", "tag": "T4", "herd": "H", "planned_kg": 10, "actual_kg": 9.9,
		                     "variance_pct": -1, "appetite": "below"},
		                    {"animal": "B", "tag": "T2", "herd": "H", "planned_kg": 10, "actual_kg": 10,
		                     "variance_pct": 0, "appetite": "on_plan"}],
		        "totals": {"planned_kg": 30, "actual_kg": 28, "below_plan": 2, "above_plan": 1, "on_plan": 1}}
		with patch("upande_livestock.serverscripts.feeding.daily_feed_report.get_daily_feed_report",
		           return_value=fake):
			f = dr.feeding(today())
			html = dr.render({**dr.build_context(today())})
		self.assertTrue(f["available"])
		self.assertEqual([a["tag"] for a in f["below"]], ["T1", "T4"])
		self.assertEqual([a["tag"] for a in f["above"]], ["T3"])
		self.assertEqual((f["below_plan"], f["above_plan"], f["on_plan"]), (2, 1, 1))
		self.assertIn("T1", html)
		self.assertIn("-30.0%", html)
		self.assertIn("+2.0%", html)
		self.assertNotIn("T2", html.split("eating less")[-1])

	def test_preview_renders_html(self):
		out = dr.preview(today())
		self.assertTrue(out["ok"], out)
		self.assertIn("Livestock daily report", out["html"])
		self.assertIn("Activities", out["html"])

	def test_settings_endpoint_roundtrip(self):
		head = make_user("zz_api@example.com")
		out = settings_api.save_daily_report_settings(
			{"enabled": 1, "time": "07:30", "head": head, "roles": ["Livestock Vet", "Livestock Vet"]})
		self.assertTrue(out["ok"], out)
		self.assertEqual((out["enabled"], out["time"], out["head"], out["roles"]),
		                 (1, "07:30", head, ["Livestock Vet"]))
		self.assertIn(head, {r["user"] for r in out["recipients"]})
		bad = settings_api.save_daily_report_settings({"time": "late"})
		self.assertIn("error", bad)
		bad = settings_api.save_daily_report_settings({"head": "nobody@nowhere.invalid"})
		self.assertIn("error", bad)

	# -- escaping, permissions, double send ----------------------------------

	def test_user_text_is_escaped_in_the_email(self):
		from unittest.mock import patch

		evil = "<script>alert(1)</script><img src=x onerror=y>"
		fake = {"herds": [{"herd": evil, "herd_name": evil, "head_count": 1, "planned_kg": 1, "actual_kg": 1, "amended": 0}],
		        "animals": [{"animal": "A", "tag": evil, "herd": evil, "planned_kg": 1, "actual_kg": 2,
		                     "variance_pct": 100, "appetite": "above"}],
		        "totals": {"planned_kg": 1, "actual_kg": 2, "below_plan": 0, "above_plan": 1, "on_plan": 0}}
		herd = make_herd("ZZ Rep X")
		cow = make_animal(herd.name)
		rec = submit_weight(cow.name, 250)
		frappe.db.set_value("Livestock Weight Record", rec.name, "remarks", f"Gallagher scale file {evil}.csv, row 2.")
		with patch("upande_livestock.serverscripts.feeding.daily_feed_report.get_daily_feed_report", return_value=fake):
			html = dr.render(dr.build_context(today()))
		self.assertNotIn("<script>", html)
		self.assertNotIn("<img src=x", html)
		self.assertIn("&lt;script&gt;", html)

	def test_preview_is_for_those_who_may_change_the_settings(self):
		reader = make_user("zz_reader@example.com", roles=["Livestock Attendant"])
		frappe.set_user(reader)
		try:
			out = dr.preview(today())
			self.assertNotIn("recipients", out)
			self.assertFalse(out.get("ok"))
		finally:
			frappe.set_user("Administrator")
		manager = make_user("zz_mgr@example.com", roles=["Livestock Manager"])
		frappe.set_user(manager)
		try:
			self.assertTrue(dr.preview(today())["ok"])
		finally:
			frappe.set_user("Administrator")

	def test_last_sent_is_not_a_form_field_and_a_stale_save_cannot_reset_it(self):
		from unittest.mock import patch

		self.assertFalse(frappe.get_meta(SETTINGS).has_field("daily_report_last_sent"))
		head = make_user("zz_stale@example.com")
		frappe.db.set_single_value(SETTINGS, "daily_report_head", head)
		frappe.db.set_single_value(SETTINGS, "daily_report_enabled", 1)
		with patch("frappe.sendmail") as mail:
			self.assertTrue(dr.send_due(now=self.at(18, 15)))
			# a desk save of the whole (stale) form
			doc = frappe.get_doc(SETTINGS)
			doc.save(ignore_permissions=True)
			self.assertFalse(dr.send_due(now=self.at(18, 30)))
			self.assertEqual(mail.call_count, 1)
		self.assertEqual(str(dr.last_sent()), today())

	def test_send_times_after_2345_are_refused_and_clamped(self):
		out = settings_api.save_daily_report_settings({"time": "23:50"})
		self.assertIn("error", out)
		self.assertTrue(settings_api.save_daily_report_settings({"time": "23:45"})["ok"])
		frappe.db.set_single_value(SETTINGS, "daily_report_enabled", 1)
		# a stored late time is treated as 23:45 so the day is not skipped
		frappe.db.set_single_value(SETTINGS, "daily_report_time", "23:59:00")
		self.assertFalse(dr.is_due(now=self.at(23, 30)))
		self.assertTrue(dr.is_due(now=self.at(23, 45)))
