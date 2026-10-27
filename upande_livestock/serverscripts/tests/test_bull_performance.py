# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Bull Performance: ranking by average daily gain inside a herd."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.performance.bull_performance import (
	get_bull_performance,
	list_performance_herds,
)
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, submit_weight


def _bull(herd, start_kg, end_kg, days=60):
	a = make_animal(herd)
	submit_weight(a.name, start_kg, days_ago=days)
	submit_weight(a.name, end_kg, days_ago=0)
	return a


class TestBullPerformance(IntegrationTestCase):
	def setUp(self):
		isolate(self)

	def test_rank_within_herd(self):
		herd = make_herd("ZZ Perf A", "Fattening", target_adg_kg=0.9).name
		a = _bull(herd, 200, 272)  # 1.2
		b = _bull(herd, 200, 248)  # 0.8
		c = _bull(herd, 200, 260)  # 1.0
		res = get_bull_performance(herd)
		rank = {r["animal"]: r["rank"] for r in res["rows"]}
		self.assertEqual((rank[a.name], rank[b.name], rank[c.name]), (1, 3, 2))
		self.assertEqual([r["rank"] for r in res["rows"]], [1, 2, 3])
		self.assertEqual(res["summary"]["head_count"], 3)
		self.assertAlmostEqual(res["summary"]["avg_period_adg"], 1.0, places=3)
		self.assertEqual(res["herd_class"], "Fattening")
		self.assertEqual(res["period_days"], 90)

	def test_unweighed_bull_unranked_and_last(self):
		herd = make_herd("ZZ Perf B", "Fattening").name
		quiet = make_animal(herd)
		one = make_animal(herd, 300)
		grower = _bull(herd, 200, 260)
		res = get_bull_performance(herd)
		self.assertEqual(res["rows"][0]["animal"], grower.name)
		by = {r["animal"]: r for r in res["rows"]}
		for a in (quiet, one):
			self.assertIsNone(by[a.name]["period_adg"])
			self.assertIsNone(by[a.name]["rank"])
			self.assertIsNone(by[a.name]["below_target"])
		self.assertIsNone(by[quiet.name]["latest_weight_kg"])
		self.assertEqual(by[one.name]["latest_weight_kg"], 300)
		self.assertEqual(by[one.name]["days_since_weighing"], 0)

	def test_below_target_uses_herd_target(self):
		herd = make_herd("ZZ Perf C", "Fattening", target_adg_kg=0.9).name
		slow = _bull(herd, 200, 248)
		fast = _bull(herd, 200, 272)
		res = get_bull_performance(herd)
		by = {r["animal"]: r for r in res["rows"]}
		self.assertTrue(by[slow.name]["below_target"])
		self.assertFalse(by[fast.name]["below_target"])
		self.assertEqual(res["target_adg_kg"], 0.9)

	def test_falls_back_to_farm_target_gday(self):
		herd = make_herd("ZZ Perf D", "Fattening").name
		frappe.db.set_single_value("Livestock Settings", "custom_target_growth_gday", 900)
		slow = _bull(herd, 200, 248)
		res = get_bull_performance(herd)
		self.assertEqual(res["target_adg_kg"], 0.9)
		self.assertTrue(res["rows"][0]["below_target"])
		self.assertEqual(res["rows"][0]["animal"], slow.name)

	def test_period_window_excludes_old_weighings(self):
		herd = make_herd("ZZ Perf E", "Fattening").name
		a = make_animal(herd)
		submit_weight(a.name, 150, days_ago=200)
		submit_weight(a.name, 300, days_ago=0)
		row = get_bull_performance(herd, 90)["rows"][0]
		self.assertIsNone(row["period_adg"])
		self.assertAlmostEqual(row["lifetime_adg"], 0.75, places=3)
		row = get_bull_performance(herd, 365)["rows"][0]
		self.assertAlmostEqual(row["period_adg"], 0.75, places=3)

	def test_list_performance_herds(self):
		fat = make_herd("ZZ Perf F", "Fattening").name
		other = make_herd("ZZ Perf G", "Cow").name
		make_animal(fat)
		listed = {h["herd"]: h for h in list_performance_herds()}
		self.assertEqual(listed[fat], {"herd": fat, "herd_class": "Fattening", "head_count": 1})
		self.assertNotIn(other, listed)


class TestBeefDashboardAndProfile(IntegrationTestCase):
	def setUp(self):
		isolate(self)

	def test_dashboard_beef_key(self):
		from upande_livestock.serverscripts.dashboard.get_livestock_workspace_stats import (
			get_livestock_workspace_stats,
		)

		herd = make_herd("ZZ Perf Dash", "Fattening").name
		_bull(herd, 200, 260)
		frappe.get_doc({
			"doctype": "Livestock Alert", "alert_kind": "Weighing Overdue", "severity": "Overdue",
			"alert_date": frappe.utils.today(), "herd": herd, "status": "Open", "message": "x",
		}).insert(ignore_permissions=True)
		before = get_livestock_workspace_stats()["beef"]
		tile = next(h for h in before["herds"] if h["herd"] == herd)
		self.assertEqual((tile["head_count"], tile["avg_weight_kg"]), (1, 260))
		self.assertAlmostEqual(tile["avg_adg_kg"], 1.0, places=3)
		self.assertGreaterEqual(before["weighings_overdue"], 1)
		for k in ("band_moves_due", "ready_for_exit"):
			self.assertIsInstance(before[k], int)

	def test_profile_gain_trend(self):
		from upande_livestock.serverscripts.animals.animal_profile import animal_profile

		herd = make_herd("ZZ Perf Prof", "Fattening", target_adg_kg=0.9).name
		a = _bull(herd, 200, 260)
		res = animal_profile({"animal": a.name})
		self.assertTrue(res.get("ok"), res.get("error"))
		self.assertEqual([p["adg_kg"] for p in res["gain"]["trend"]], [None, 1.0])
		self.assertAlmostEqual(res["gain"]["lifetime_adg"], 1.0, places=3)
		self.assertEqual(res["gain"]["target_adg_kg"], 0.9)
