# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The production-forecast endpoints, the buyer commitments and the weekly snapshot.

Herds, bulls and weighings are built inside each test (beef_fixtures) and rolled
back with it. Every forecast call is scoped to the test's own herd so bulls
already on the site do not leak into the numbers.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from upande_livestock.serverscripts.forecast.accuracy import get_forecast_accuracy
from upande_livestock.serverscripts.forecast.commitments import list_buyer_commitments, save_buyer_commitment
from upande_livestock.serverscripts.forecast.cover import get_commitment_cover
from upande_livestock.serverscripts.forecast.output import get_output_forecast
from upande_livestock.serverscripts.forecast.snapshot import take_weekly_snapshot
from upande_livestock.serverscripts.tests.beef_fixtures import (
	clear_bands,
	isolate,
	make_animal,
	make_herd,
	submit_weight,
)

SNAPSHOT = "Livestock Forecast Snapshot"


def _monday(day):
	day = getdate(day)
	return add_days(day, -day.weekday())


def _customer():
	return frappe.get_doc({
		"doctype": "Customer", "customer_name": "ZZ Buyer " + frappe.generate_hash(length=6),
		"customer_group": "Individual", "territory": "Kenya",
	}).insert(ignore_permissions=True).name


def _fattening_herd(name):
	"""An open-ended Fattening herd, so the exit weight is the farm setting (450)."""
	clear_bands()
	return make_herd(name, "Fattening", 0, 0).name


def _bull_ready_in_20_days(herd):
	"""400 kg 30 days ago, 430 kg today: 1.0 kg/day, so 450 kg is 20 days away."""
	a = make_animal(herd)
	submit_weight(a.name, 400, days_ago=30)
	submit_weight(a.name, 430, days_ago=0)
	return a


class TestForecastEndpoints(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		frappe.db.set_single_value("Livestock Settings", "target_exit_weight_kg", 450)

	def test_output_forecast_ready_week(self):
		herd = _fattening_herd("ZZ Fcst Out")
		bull = _bull_ready_in_20_days(herd)
		res = get_output_forecast(weeks=12, herd=herd)

		ready = add_days(getdate(today()), 20)
		self.assertEqual(res["exit_weight_kg"], 450)
		self.assertEqual(res["horizon_weeks"], 12)
		self.assertEqual(len(res["weeks"]), 12)
		row = next(b for b in res["bulls"] if b["animal"] == bull.name)
		self.assertEqual(row["ready_date"], str(ready))
		self.assertEqual(row["ready_week"], str(_monday(ready)))
		self.assertEqual(row["adg_source"], "own")
		self.assertAlmostEqual(row["forecast_adg"], 1.0, places=3)
		week = next(w for w in res["weeks"] if w["week_start"] == str(_monday(ready)))
		self.assertEqual(week["head"], 1)
		self.assertAlmostEqual(week["kg"], 450.0, places=1)
		self.assertEqual(sum(w["head"] for w in res["weeks"]), 1)
		self.assertEqual(res["unforecastable"], 0)

	def test_unweighed_bull_is_unforecastable(self):
		herd = _fattening_herd("ZZ Fcst Quiet")
		_bull_ready_in_20_days(herd)
		make_animal(herd)  # no weighing at all
		res = get_output_forecast(weeks=12, herd=herd)
		self.assertEqual(len(res["bulls"]), 1)
		self.assertEqual(res["unforecastable"], 1)

	def test_cover_uses_open_commitments_only(self):
		herd = _fattening_herd("ZZ Fcst Cover")
		_bull_ready_in_20_days(herd)
		customer = _customer()
		ready_week = _monday(add_days(getdate(today()), 20))
		for head, status in ((3, "Open"), (5, "Cancelled"), (7, "Fulfilled")):
			frappe.get_doc({
				"doctype": "Livestock Buyer Commitment", "customer": customer,
				"week_start": ready_week, "head": head, "status": status,
			}).insert(ignore_permissions=True)

		res = get_commitment_cover(weeks=12)
		row = next(r for r in res["weeks"] if r["week_start"] == str(ready_week))
		self.assertEqual(row["committed_head"], 3)

	def test_accuracy_reads_prior_snapshot_and_disposals(self):
		frappe.db.delete(SNAPSHOT)
		last_week = add_days(_monday(getdate(today())), -7)

		def snap(taken, head, kg):
			frappe.get_doc({
				"doctype": SNAPSHOT, "snapshot_date": taken, "week_start": last_week,
				"forecast_head": head, "forecast_kg": kg,
			}).insert(ignore_permissions=True)

		snap(add_days(last_week, -10), 9, 4000)  # older: superseded
		snap(add_days(last_week, -3), 4, 1800)  # the latest one before the week
		snap(last_week, 7, 3000)  # taken on the week's first day: not "before"

		with patch(
			"upande_livestock.serverscripts.forecast.data.disposal_actuals", return_value=(3, 1350.0)
		) as actuals:
			res = get_forecast_accuracy(weeks=2)

		self.assertEqual(len(res["weeks"]), 2)
		row = next(w for w in res["weeks"] if w["week_start"] == str(last_week))
		self.assertEqual(row["snapshot_date"], str(add_days(last_week, -3)))
		self.assertEqual((row["forecast_head"], row["actual_head"]), (4, 3))
		self.assertEqual((row["forecast_kg"], row["actual_kg"]), (1800, 1350.0))
		self.assertAlmostEqual(row["error_pct_head"], -0.25, places=4)
		self.assertAlmostEqual(row["error_pct_kg"], -0.25, places=4)
		self.assertTrue(actuals.called)

		# The week before has no snapshot: nothing forecast, so no error either.
		earlier = next(w for w in res["weeks"] if w["week_start"] == str(add_days(last_week, -7)))
		self.assertIsNone(earlier["forecast_head"])
		self.assertIsNone(earlier["error_pct_head"])

	def test_snapshot_idempotent_same_day(self):
		herd = _fattening_herd("ZZ Fcst Snap")
		_bull_ready_in_20_days(herd)
		first = take_weekly_snapshot()
		self.assertGreater(first, 0)
		self.assertEqual(frappe.db.count(SNAPSHOT, {"snapshot_date": today()}), first)
		second = take_weekly_snapshot()
		self.assertEqual(second, first)
		self.assertEqual(frappe.db.count(SNAPSHOT, {"snapshot_date": today()}), first)
		# The farm rows (no herd) and this herd's rows are both there.
		self.assertTrue(frappe.db.exists(SNAPSHOT, {"snapshot_date": today(), "herd": herd}))
		self.assertTrue(frappe.db.exists(SNAPSHOT, {"snapshot_date": today(), "herd": ["is", "not set"]}))

	def test_commitment_week_normalised_to_monday(self):
		customer = _customer()
		wednesday = add_days(_monday(getdate(today())), 9)  # a Wednesday next week
		res = save_buyer_commitment({"customer": customer, "week_start": str(wednesday), "head": 4})
		self.assertTrue(res.get("ok"), res)
		self.assertEqual(frappe.db.get_value("Livestock Buyer Commitment", res["name"], "week_start"),
		                 _monday(wednesday))

		# Update by name, then list.
		res2 = save_buyer_commitment({"name": res["name"], "head": 6, "status": "Fulfilled"})
		self.assertEqual(res2, {"ok": True, "name": res["name"]})
		rows = list_buyer_commitments(status="Fulfilled", from_week=str(_monday(wednesday)))
		self.assertIn(res["name"], [r["name"] for r in rows])

	def test_commitment_needs_positive_head(self):
		res = save_buyer_commitment({"customer": _customer(), "week_start": today(), "head": 0})
		self.assertIn("error", res)
