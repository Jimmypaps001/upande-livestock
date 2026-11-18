# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A herd's feed day: the recipe is the plan, what was fed is the actual.

Amending changes the day's actuals and never the recipe; manufacturing mixes the
actuals and, when the store is short, leaves the mix as a draft dated that day;
the per-animal figures divide the herd's actual by the head fed; the daily
report flags appetite by variance from the plan.

    bench --site mutara.local run-tests --app upande_livestock \
        --module upande_livestock.serverscripts.tests.test_feed_actuals

The shortage is made, not found (as in test_feed_drafts), so these do not
depend on what the farm's stores hold today.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.feeding import _availability
from upande_livestock.serverscripts.feeding import _engine as feeding
from upande_livestock.serverscripts.feeding import daily_feed_report as report
from upande_livestock.serverscripts.feeding import feed_actuals as FA
from upande_livestock.serverscripts.feeding._units import is_kg


class TestAppetiteFlags(unittest.TestCase):
	"""No threshold: any shortfall is below, any excess above, 0.01 kg rounds to on plan."""

	def test_any_variance_is_below_or_above(self):
		self.assertEqual(report.appetite_flag(-0.5), "below")
		self.assertEqual(report.appetite_flag(-0.02), "below")
		self.assertEqual(report.appetite_flag(0.02), "above")
		self.assertEqual(report.appetite_flag(40), "above")

	def test_under_a_hundredth_of_a_kilo_is_on_plan(self):
		for kg in (0, 0.004, -0.004, -0.0049):
			self.assertEqual(report.appetite_flag(kg), "on_plan")

	def test_variance_percent(self):
		self.assertEqual(FA.variance_pct(200, 300), 50.0)
		self.assertEqual(FA.variance_pct(200, 150), -25.0)
		self.assertEqual(FA.variance_pct(0, 50), 0.0)

	def test_no_threshold_constants_remain(self):
		self.assertFalse(hasattr(report, "LOW_APPETITE_PCT"))
		self.assertFalse(hasattr(report, "HIGH_APPETITE_PCT"))


def _short(real):
	"""resolve_requirement, with its first line reported short."""

	def wrapped(*args, **kwargs):
		bom, lines = real(*args, **kwargs)
		lines = [dict(ln) for ln in lines]
		if lines:
			lines[0]["short_qty"] = lines[0]["required_qty"]
		return bom, lines

	return wrapped


class TestFeedActuals(IntegrationTestCase):
	def setUp(self):
		self.herd = None
		for h in frappe.get_all("Herds", filters=[["bom", "is", "set"]], pluck="name", order_by="name asc"):
			try:
				heads = feeding._herd_bom(h)[2]
			except frappe.ValidationError:
				continue
			if heads > 0 and not FA._is_mixed(h, today()) and not FA._record_name(h, today()):
				self.herd, self.heads = h, heads
				break
		if not self.herd:
			raise unittest.SkipTest("no herd with a recipe, animals and an unfed today")
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		self.addCleanup(self._clean)
		self.events = []

	def _clean(self):
		for ev in self.events:
			if frappe.db.get_value("Livestock Event", ev, "docstatus") == 1:
				frappe.get_doc("Livestock Event", ev).cancel()
		name = FA._record_name(self.herd, today())
		if name:
			frappe.delete_doc(FA.DOCTYPE, name, force=True, ignore_permissions=True)

	def _day(self, on=None):
		return FA.herd_day(self.herd, on or today())

	def test_the_plan_is_each_line_per_head_times_head_count(self):
		day = self._day()
		bom = frappe.get_doc("BOM", frappe.db.get_value("Herds", self.herd, "bom"))
		self.assertEqual(day["head_count"], self.heads)
		for line, comp in zip(bom.items, day["components"]):
			self.assertAlmostEqual(comp["planned_kg"], flt(line.qty) * self.heads, places=2)
			self.assertAlmostEqual(comp["planned_per_head"] * self.heads, comp["planned_kg"], places=2)
			# Without an amendment the actual is the plan.
			self.assertEqual(comp["actual_kg"], comp["planned_kg"])
		self.assertFalse(day["amended"])
		self.assertEqual(day["status"], "Planned")
		self.assertEqual(day["actual_kg"], day["planned_kg"])

	def test_amending_changes_the_actuals_and_never_the_recipe(self):
		bom_name = frappe.db.get_value("Herds", self.herd, "bom")
		before = [(r.item_code, r.qty) for r in frappe.get_doc("BOM", bom_name).items]
		item = self._day()["components"][0]
		out = FA.amend_day(self.herd, today(), [{"item_code": item["item_code"], "actual_kg": item["planned_kg"] + 100}])
		self.assertTrue(out["amended"])
		self.assertEqual(out["status"], "Amended")
		first = out["components"][0]
		self.assertAlmostEqual(first["actual_kg"], item["planned_kg"] + 100, places=2)
		self.assertAlmostEqual(first["planned_kg"], item["planned_kg"], places=2)
		self.assertAlmostEqual(out["variance_kg"], 100, places=2)
		# The recipe is exactly as it was, and the herd still points at it.
		after = [(r.item_code, r.qty) for r in frappe.get_doc("BOM", bom_name).items]
		self.assertEqual(before, after)
		self.assertEqual(frappe.db.get_value("Herds", self.herd, "bom"), bom_name)
		# The other components keep their plan.
		for comp in out["components"][1:]:
			self.assertEqual(comp["actual_kg"], comp["planned_kg"])

	def test_a_second_amend_updates_the_same_record(self):
		code = self._day()["components"][0]["item_code"]
		FA.amend_day(self.herd, today(), [{"item_code": code, "actual_kg": 5}])
		FA.amend_day(self.herd, today(), {code: 7})
		self.assertEqual(frappe.db.count(FA.DOCTYPE, {"herd": self.herd, "date": today()}), 1)
		self.assertEqual(self._day()["components"][0]["actual_kg"], 7)

	def test_a_negative_amount_or_an_unknown_item_is_refused(self):
		code = self._day()["components"][0]["item_code"]
		with self.assertRaises(frappe.ValidationError):
			FA.amend_day(self.herd, today(), [{"item_code": code, "actual_kg": -1}])
		with self.assertRaises(frappe.ValidationError):
			FA.amend_day(self.herd, today(), [{"item_code": "no such feed", "actual_kg": 1}])

	def test_a_future_day_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			FA.herd_day(self.herd, add_days(today(), 2))

	def test_per_animal_intake_divides_the_actual_by_the_head_fed(self):
		code = self._day()["components"][0]["item_code"]
		out = FA.amend_day(self.herd, today(), [{"item_code": code, "actual_kg": 1000}])
		intake = FA.per_animal_intake(self.herd, today())
		self.assertEqual(intake["head_count"], self.heads)
		self.assertAlmostEqual(intake["actual_kg"], out["actual_kg"] / self.heads, places=2)
		self.assertAlmostEqual(intake["planned_kg"], out["planned_kg"] / self.heads, places=2)
		self.assertAlmostEqual(intake["variance_kg"], intake["actual_kg"] - intake["planned_kg"], places=2)
		for a in intake["animals"]:
			self.assertEqual(a["actual_kg"], intake["actual_kg"])
			self.assertEqual(a["planned_kg"], intake["planned_kg"])

	def _manufacture_short(self, **kw):
		with patch.object(feeding, "resolve_requirement", side_effect=_short(feeding.resolve_requirement)):
			res = FA.manufacture_day(self.herd, today(), employee=self.employee, **kw)
		if res["engine"].get("livestock_event"):
			self.events.append(res["engine"]["livestock_event"])
		return res

	def test_manufacturing_with_short_stock_leaves_a_draft_dated_that_day(self):
		if not self.employee:
			self.skipTest("no active Employee on this site")
		item = self._day()["components"][0]
		FA.amend_day(self.herd, today(), [{"item_code": item["item_code"], "actual_kg": item["planned_kg"] + 400}])
		res = self._manufacture_short()
		self.assertTrue(res["pending"])
		self.assertEqual(res["status"], "Waiting for stock")
		transfer = frappe.get_doc("Stock Entry", res["stock"]["transfer_stock_entry"])
		self.assertEqual(transfer.docstatus, 0)
		self.assertEqual(str(transfer.posting_date), today())
		self.assertEqual(res["draft_entries"], [transfer.name])
		# The draft records what was fed, not the recipe's plan: the Work Order
		# consumes the amended quantity of the first component.
		wo = frappe.get_doc("Work Order", res["stock"]["work_order"])
		row = next(r for r in wo.required_items if r.item_code == item["item_code"])
		planned_row = next(r for r in FA._plan(self.herd)[2] if r["item_code"] == item["item_code"])
		cf = flt(
			frappe.db.get_value("BOM Item", {"parent": wo.bom_no, "item_code": item["item_code"]}, "conversion_factor")
		) or 1.0
		self.assertAlmostEqual(flt(row.required_qty), (item["planned_kg"] + 400) * cf, delta=0.05 + 0.001 * flt(row.required_qty))
		self.assertNotEqual(wo.bom_no, frappe.db.get_value("Herds", self.herd, "bom"))
		# Nothing was mixed or issued, and the day cannot be fed or amended twice.
		self.assertFalse(res["stock"].get("issue_stock_entry"))
		with self.assertRaises(frappe.ValidationError):
			FA.manufacture_day(self.herd, today(), employee=self.employee)
		with self.assertRaises(frappe.ValidationError):
			FA.amend_day(self.herd, today(), [{"item_code": item["item_code"], "actual_kg": 1}])
		self.assertIsNotNone(planned_row)

	def test_an_unamended_day_mixes_the_recipe_as_it_is(self):
		if not self.employee:
			self.skipTest("no active Employee on this site")
		res = self._manufacture_short()
		self.assertTrue(res["pending"])
		self.assertEqual(res["engine"]["bom_no"], frappe.db.get_value("Herds", self.herd, "bom"))

	def test_a_backdated_short_day_is_drafted_not_refused(self):
		if not self.employee:
			self.skipTest("no active Employee on this site")
		past = add_days(today(), -3)
		if FA._is_mixed(self.herd, past) or FA._record_name(self.herd, past):
			self.skipTest("that day is already fed")
		self.addCleanup(
			lambda: frappe.db.exists(FA.DOCTYPE, {"herd": self.herd, "date": past})
			and frappe.delete_doc(
				FA.DOCTYPE, FA._record_name(self.herd, past), force=True, ignore_permissions=True
			)
		)
		with patch("upande_livestock.serverscripts.common.backdate.window_open", return_value=True), patch.object(
			_availability, "get_stock_balance", return_value=0
		):
			res = FA.manufacture_day(self.herd, past, employee=self.employee)
		if res["engine"].get("livestock_event"):
			self.events.append(res["engine"]["livestock_event"])
		self.assertTrue(res["pending"])
		transfer = frappe.get_doc("Stock Entry", res["stock"]["transfer_stock_entry"])
		self.assertEqual(transfer.docstatus, 0)
		self.assertEqual(str(transfer.posting_date), past)

	def test_the_report_flags_appetite_against_the_plan(self):
		item = self._day()["components"][0]
		if not is_kg(item["uom"]):
			self.skipTest("first recipe line is not a kilogram line")
		planned_total = self._day()["planned_kg"]
		FA.amend_day(self.herd, today(), [{"item_code": item["item_code"], "actual_kg": item["planned_kg"] + planned_total * 0.5}])
		frappe.db.set_value(FA.DOCTYPE, FA._record_name(self.herd, today()), "status", "Manufactured")
		with patch.object(report, "_weights", return_value={}):
			out = report.get_daily_feed_report(today(), self.herd)
		self.assertEqual(out["date"], today())
		self.assertEqual([h["herd"] for h in out["herds"]], [self.herd])
		herd = out["herds"][0]
		self.assertTrue(herd["amended"])
		self.assertEqual(herd["head_count"], self.heads)
		self.assertGreater(herd["actual_kg"], herd["planned_kg"])
		self.assertEqual(
			set(herd["components"][0]), {"item_code", "item_name", "uom", "planned_kg", "actual_kg"}
		)
		self.assertTrue(out["animals"], "the herd has animals on this site")
		for a in out["animals"]:
			self.assertEqual(a["herd"], self.herd)
			self.assertGreater(a["variance_pct"], 0)
			self.assertEqual(a["appetite"], "above")
			self.assertAlmostEqual(a["variance_kg"], a["actual_kg"] - a["planned_kg"], places=2)
			for key in ("tag", "last_weight", "last_weight_date", "adg"):
				self.assertIn(key, a)
		self.assertEqual(
			{k: out["totals"][k] for k in ("below_plan", "above_plan", "on_plan")},
			{"below_plan": 0, "above_plan": len(out["animals"]), "on_plan": 0},
		)
		self.assertNotIn("low_appetite", out["totals"])
		self.assertAlmostEqual(out["totals"]["actual_kg"], herd["actual_kg"], places=2)

	def test_a_herd_not_fed_that_day_is_not_in_the_report(self):
		out = report.get_daily_feed_report(today(), self.herd)
		self.assertEqual(out["herds"], [])
		self.assertEqual(out["animals"], [])
		self.assertEqual(out["totals"]["actual_kg"], 0)

	def test_a_shortfall_is_below_plan(self):
		item = self._day()["components"][0]
		if not is_kg(item["uom"]):
			self.skipTest("first recipe line is not a kilogram line")
		FA.amend_day(self.herd, today(), [
			{"item_code": c["item_code"], "actual_kg": c["planned_kg"] * 0.5} for c in self._day()["components"]
		])
		frappe.db.set_value(FA.DOCTYPE, FA._record_name(self.herd, today()), "status", "Manufactured")
		with patch.object(report, "_weights", return_value={}):
			out = report.get_daily_feed_report(today(), self.herd)
		self.assertTrue(all(a["appetite"] == "below" for a in out["animals"]))
		self.assertEqual(out["totals"]["below_plan"], len(out["animals"]))
		self.assertEqual(out["totals"]["above_plan"] + out["totals"]["on_plan"], 0)

	def test_a_tiny_shortfall_is_still_below_and_the_whole_report_has_no_band(self):
		item = self._day()["components"][0]
		if not is_kg(item["uom"]):
			self.skipTest("first recipe line is not a kilogram line")
		planned_total = self._day()["planned_kg"]
		# about 1% of the plan: the old band would have called this normal.
		FA.amend_day(self.herd, today(), [
			{"item_code": item["item_code"], "actual_kg": item["planned_kg"] - planned_total * 0.01}
		])
		frappe.db.set_value(FA.DOCTYPE, FA._record_name(self.herd, today()), "status", "Manufactured")
		with patch.object(report, "_weights", return_value={}):
			out = report.get_daily_feed_report(today(), self.herd)
		for a in out["animals"]:
			self.assertEqual(a["appetite"], "below")
			self.assertLess(a["variance_pct"], 0)
		intake = FA.per_animal_intake(self.herd, today())
		self.assertEqual(intake["appetite"], "below")
		self.assertEqual(intake["totals"]["below_plan"], len(intake["animals"]))

	def test_an_unamended_day_is_on_plan(self):
		intake = FA.per_animal_intake(self.herd, today())
		self.assertEqual(intake["appetite"], "on_plan")
		self.assertTrue(all(a["appetite"] == "on_plan" for a in intake["animals"]))
		self.assertEqual(intake["totals"]["on_plan"], len(intake["animals"]))

	# -- removing an item, resetting, and the recipe loading every day -----

	def test_an_item_can_be_removed_for_the_day_and_is_left_out_of_the_mix(self):
		comps = self._day()["components"]
		if len(comps) < 2:
			self.skipTest("the recipe has one line")
		gone = comps[0]["item_code"]
		out = FA.amend_day(self.herd, today(), [{"item_code": gone, "actual_kg": 0}])
		row = next(c for c in out["components"] if c["item_code"] == gone)
		self.assertEqual(row["actual_kg"], 0)
		self.assertTrue(row["removed"])
		self.assertTrue(out["amended"])
		self.assertNotIn(gone, [ln["item_code"] for ln in FA._actual_lines(out, 1)])
		self.assertTrue(all(not c["removed"] for c in out["components"] if c["item_code"] != gone))

	def test_reset_puts_the_day_back_to_the_recipe(self):
		code = self._day()["components"][0]["item_code"]
		FA.amend_day(self.herd, today(), [{"item_code": code, "actual_kg": 0}])
		self.assertTrue(FA._record_name(self.herd, today()))
		out = FA.reset_day(self.herd, today())
		self.assertFalse(out["record"])
		self.assertFalse(out["amended"])
		self.assertEqual(out["status"], "Planned")
		self.assertTrue(all(c["actual_kg"] == c["planned_kg"] and not c["removed"] for c in out["components"]))
		# resetting a day that was never amended is harmless
		self.assertFalse(FA.reset_day(self.herd, today())["amended"])

	def test_reset_is_refused_once_the_day_is_mixed(self):
		code = self._day()["components"][0]["item_code"]
		FA.amend_day(self.herd, today(), [{"item_code": code, "actual_kg": 3}])
		frappe.db.set_value(FA.DOCTYPE, FA._record_name(self.herd, today()), "status", "Manufactured")
		with self.assertRaises(frappe.ValidationError):
			FA.reset_day(self.herd, today())
		self.assertTrue(FA._record_name(self.herd, today()))

	def test_an_amendment_belongs_to_its_day_and_the_next_day_loads_the_recipe(self):
		past = add_days(today(), -1)
		if FA._is_mixed(self.herd, past) or FA._record_name(self.herd, past):
			self.skipTest("yesterday is already fed")
		self.addCleanup(
			lambda: frappe.db.exists(FA.DOCTYPE, {"herd": self.herd, "date": past})
			and frappe.delete_doc(FA.DOCTYPE, FA._record_name(self.herd, past), force=True, ignore_permissions=True)
		)
		bom_name = frappe.db.get_value("Herds", self.herd, "bom")
		before = [(r.item_code, r.qty) for r in frappe.get_doc("BOM", bom_name).items]
		comps = self._day(past)["components"]
		FA.amend_day(self.herd, past, [{"item_code": comps[0]["item_code"], "actual_kg": 0}])
		FA.amend_day(self.herd, past, [{"item_code": c["item_code"], "actual_kg": c["planned_kg"] * 2} for c in comps[1:]])
		self.assertTrue(FA.herd_day(self.herd, past)["amended"])
		# the following day loads the recipe's plan: actual = plan, nothing removed
		nxt = FA.herd_day(self.herd, today())
		self.assertFalse(nxt["amended"])
		self.assertIsNone(nxt["record"])
		for line, c in zip(FA._plan(self.herd)[2], nxt["components"]):
			self.assertEqual(c["item_code"], line["item_code"])
			self.assertEqual(c["actual_kg"], line["planned"])
			self.assertEqual(c["planned_kg"], line["planned"])
			self.assertFalse(c["removed"])
		self.assertEqual(before, [(r.item_code, r.qty) for r in frappe.get_doc("BOM", bom_name).items])
		self.assertEqual(frappe.db.get_value("Herds", self.herd, "bom"), bom_name)

	# -- a day does not stay stuck ----------------------------------------

	def test_a_day_whose_entries_are_gone_returns_to_planned_or_amended(self):
		code = self._day()["components"][0]["item_code"]
		FA.amend_day(self.herd, today(), [{"item_code": code, "actual_kg": 3}])
		name = FA._record_name(self.herd, today())
		frappe.db.set_value(
			FA.DOCTYPE, name, {"status": "Manufactured", "transfer_stock_entry": "MAT-STE-NO-SUCH-ENTRY"}
		)
		self.assertFalse(FA._is_mixed(self.herd, today()))
		doc = frappe.get_doc(FA.DOCTYPE, name)
		self.assertEqual(doc.status, "Amended")
		self.assertFalse(doc.transfer_stock_entry)
		# and it can be amended again
		FA.amend_day(self.herd, today(), [{"item_code": code, "actual_kg": 4}])

	def test_a_deleted_draft_frees_the_day_and_a_posted_one_makes_it_manufactured(self):
		if not self.employee:
			self.skipTest("no active Employee on this site")
		code = self._day()["components"][0]["item_code"]
		FA.amend_day(self.herd, today(), [{"item_code": code, "actual_kg": self._day()["components"][0]["planned_kg"] + 50}])
		res = self._manufacture_short()
		self.assertEqual(res["status"], "Waiting for stock")
		draft = res["stock"]["transfer_stock_entry"]
		name = FA._record_name(self.herd, today())
		# posted: the status follows (the posting itself is faked at the row)
		frappe.db.set_value("Stock Entry", draft, "docstatus", 1)
		self.assertEqual(FA.resync_record(name), "Manufactured")
		frappe.db.set_value("Stock Entry", draft, "docstatus", 0)
		frappe.db.set_value(FA.DOCTYPE, name, "status", "Waiting for stock")
		# deleted: the hook unlinks it and the day falls back to Amended
		frappe.delete_doc("Stock Entry", draft, force=True, ignore_permissions=True)
		doc = frappe.get_doc(FA.DOCTYPE, name)
		self.assertEqual(doc.status, "Amended")
		self.assertFalse(doc.transfer_stock_entry)
		self.assertFalse(FA._is_mixed(self.herd, today()))
		FA.amend_day(self.herd, today(), [{"item_code": code, "actual_kg": 5}])

	def test_manufacture_locks_the_day_record_first(self):
		if not self.employee:
			self.skipTest("no active Employee on this site")
		code = self._day()["components"][0]["item_code"]
		FA.amend_day(self.herd, today(), [{"item_code": code, "actual_kg": 9}])
		seen = []
		real = FA._is_mixed
		with patch.object(FA, "_is_mixed", side_effect=lambda *a, **k: seen.append(k) or real(*a, **k)):
			try:
				self._manufacture_short()
			except Exception:
				pass
		self.assertTrue(seen and seen[0].get("for_update"))
