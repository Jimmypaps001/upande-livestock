# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Weight-based appreciation of the animal asset (common/appreciation)."""

import unittest
from datetime import datetime

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.common import appreciation as A
from upande_livestock.serverscripts.common import calf_asset
from upande_livestock.serverscripts.tests.test_calf_asset import CalfAssetCase
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge, _purge_events_for


def row(**kw):
	return frappe._dict({"idx": 1, "price_per_kg": 100, **kw})


class TestMatrixLookup(IntegrationTestCase):
	def test_first_priced_row_that_fits_wins(self):
		rows = [row(idx=1, band="Cow", price_per_kg=0), row(idx=2, band="Cow", price_per_kg=150),
		        row(idx=3, price_per_kg=90)]
		self.assertEqual(A.matching_row(rows, "Cow", "Female", 50, 400).idx, 2)
		# A zero price never matches, a blank band fits anything.
		self.assertEqual(A.matching_row(rows, "Bull", "Male", 50, 400).idx, 3)

	def test_age_and_weight_ranges(self):
		rows = [row(idx=1, age_from_months=6, age_to_months=12, weight_from_kg=100, weight_to_kg=200)]
		self.assertTrue(A.matching_row(rows, None, None, 6, 100))
		self.assertFalse(A.matching_row(rows, None, None, 12, 150))  # upper age is exclusive
		self.assertFalse(A.matching_row(rows, None, None, 8, 200))   # so is the weight
		self.assertFalse(A.matching_row(rows, None, None, None, 150))  # unknown age cannot fit an age range
		self.assertFalse(A.matching_row(rows, None, None, 8, 99))

	def test_sex_must_agree(self):
		self.assertFalse(A.matching_row([row(sex="Male")], "Calf", "Female", 1, 50))

	def test_cap(self):
		self.assertEqual(A.value_for(row(price_per_kg=200, max_value=50000), 300), (50000, True))
		self.assertEqual(A.value_for(row(price_per_kg=200), 300), (60000, False))

	def test_bands(self):
		f = frappe._dict
		self.assertEqual(A.band_of(f(sex="Female"), 3), "Calf")
		self.assertEqual(A.band_of(f(sex="Male"), 8), "Weaner")
		self.assertEqual(A.band_of(f(sex="Male"), 20), "Bull")
		self.assertEqual(A.band_of(f(sex="Female"), 18), "Heifer")
		self.assertEqual(A.band_of(f(sex="Female", repro_status="Pregnant"), 18), "In-calf Heifer")
		self.assertEqual(A.band_of(f(sex="Female", parity=1), 30), "Cow")
		self.assertIsNone(A.band_of(f(sex="Female"), None))


class TestDueCheck(IntegrationTestCase):
	def due(self, when, freq, hour, last=None):
		return A.is_due(datetime.fromisoformat(when), freq, hour, last)

	def test_daily(self):
		self.assertFalse(self.due("2026-11-18 01:30", "Daily", 2))
		self.assertTrue(self.due("2026-11-18 02:05", "Daily", 2))
		self.assertFalse(self.due("2026-11-18 03:05", "Daily", 2))  # never run: waits for its hour
		self.assertTrue(self.due("2026-11-18 03:05", "Daily", 2, "2026-11-17 02:10"))  # missed hour is made up
		self.assertFalse(self.due("2026-11-18 03:05", "Daily", 2, "2026-11-18 02:10"))  # already ran

	def test_weekly_is_monday(self):
		self.assertTrue(self.due("2026-11-16 02:00", "Weekly", 2))   # Monday
		self.assertFalse(self.due("2026-11-17 02:00", "Weekly", 2))  # Tuesday, never run
		self.assertTrue(self.due("2026-11-17 02:00", "Weekly", 2, "2026-11-09 02:05"))
		self.assertFalse(self.due("2026-11-19 02:00", "Weekly", 2, "2026-11-16 02:05"))

	def test_monthly_is_the_first(self):
		self.assertTrue(self.due("2026-12-01 05:00", "Monthly", 5))
		self.assertFalse(self.due("2026-12-02 05:00", "Monthly", 5))
		self.assertTrue(self.due("2026-12-02 05:00", "Monthly", 5, "2026-11-01 05:10"))
		self.assertFalse(self.due("2026-12-20 05:00", "Monthly", 5, "2026-12-01 05:10"))

	def test_run_if_due_does_nothing_when_switched_off(self):
		from unittest import mock

		with mock.patch.object(A, "is_enabled", return_value=False), mock.patch.object(A, "run") as run:
			self.assertIsNone(A.run_if_due())
		run.assert_not_called()

	def test_run_if_due_runs_when_due(self):
		from unittest import mock

		with mock.patch.object(A, "is_enabled", return_value=True), \
				mock.patch.object(A, "is_due", return_value=True), \
				mock.patch.object(A, "run", return_value={"ok": 1}) as run:
			self.assertEqual(A.run_if_due(), {"ok": 1})
		run.assert_called_once_with(dry_run=0)


class TestPosting(CalfAssetCase):
	"""Real assets and adjustments; everything made here is cancelled and removed."""

	def setUp(self):
		super().setUp()
		if not frappe.db.get_single_value("Livestock Settings", "custom_default_company"):
			raise unittest.SkipTest("no default company")
		self.animal = _make_cow("ZZ APPR HEIFER", months_old=18)
		self.addCleanup(_purge_events_for, self.animal.name)
		self.addCleanup(self.clean_animal)
		calf_asset.create_calf_asset(self.animal.name)
		self.animal.reload()
		if not self.animal.asset_link:
			raise unittest.SkipTest("asset could not be raised on this site")
		self.asset = self.animal.asset_link
		company = frappe.db.get_value("Asset", self.asset, "company")
		self.account = frappe.db.get_value(
			"Account", {"company": company, "root_type": "Income", "is_group": 0}, "name")
		if not self.account:
			raise unittest.SkipTest("no income account")
		self.set_weight(400)

	def clean_animal(self):
		for ava in frappe.get_all("Asset Value Adjustment", filters={"asset": self.asset}, pluck="name"):
			doc = frappe.get_doc("Asset Value Adjustment", ava)
			je = doc.journal_entry
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Asset Value Adjustment", ava, force=True, ignore_permissions=True)
			if je and frappe.db.exists("Journal Entry", je):
				frappe.delete_doc("Journal Entry", je, force=True, ignore_permissions=True)
		_purge("Animal", self.animal.name)

	def set_weight(self, kg):
		frappe.db.set_value("Animal", self.animal.name, "last_weight_kg", kg, update_modified=False)
		# the test animal has no Weight Records, so the Animal's own figure is the weighing
		for rec in frappe.get_all("Livestock Weight Record", filters={"animal": self.animal.name}, pluck="name"):
			frappe.delete_doc("Livestock Weight Record", rec, force=True, ignore_permissions=True)

	def settings(self, price=300, **kw):
		s = frappe.get_single("Livestock Settings")
		s.set(A.MATRIX, [])
		s.append(A.MATRIX, {"band": "Heifer", "price_per_kg": price, **kw})
		s.appreciation_enabled = 1
		s.appreciation_account = self.account
		s.appreciation_min_change = 500
		s.appreciation_allow_decrease = 0
		return s

	def value(self):
		return A.asset_book_value(self.asset)

	def test_appraise_uses_band_weight_and_price(self):
		a = A.appraise(self.animal.name, s=self.settings())
		self.assertEqual(a["value"], 120000)
		self.assertEqual(a["basis"]["band"], "Heifer")
		self.assertEqual(a["basis"]["weight_kg"], 400)
		self.assertEqual(a["basis"]["row"], 1)

	def test_dry_run_posts_nothing(self):
		r = A.post_appreciation(self.animal.name, dry_run=1, s=self.settings())
		self.assertEqual(r["status"], "would_post")
		self.assertEqual(r["difference"], 120000 - 5000)
		self.assertEqual(self.value(), 5000)
		self.assertFalse(frappe.db.exists("Asset Value Adjustment", {"asset": self.asset}))

	def test_post_raises_the_asset_and_is_idempotent(self):
		r = A.post_appreciation(self.animal.name, dry_run=0, s=self.settings())
		self.assertEqual(r["status"], "posted", r)
		self.assertEqual(self.value(), 120000)
		ava = frappe.get_doc("Asset Value Adjustment", r["adjustment"])
		self.assertEqual(ava.docstatus, 1)
		self.assertEqual(ava.difference_account, self.account)
		self.assertTrue(ava.livestock_weight_ref)
		self.assertEqual(frappe.db.get_value("Journal Entry Account",
		                 {"parent": ava.journal_entry, "account": self.account}, "credit_in_account_currency"), 115000)

		again = A.post_appreciation(self.animal.name, dry_run=0, s=self.settings())
		self.assertEqual(again["status"], "skipped")
		self.assertIn("already posted", again["reason"])
		self.assertEqual(frappe.db.count("Asset Value Adjustment", {"asset": self.asset, "docstatus": 1}), 1)
		self.assertEqual(self.value(), 120000)

	def test_below_the_minimum_is_left(self):
		A.post_appreciation(self.animal.name, dry_run=0, s=self.settings())
		self.set_weight(401)  # a new weighing worth 300, under the 500 minimum
		r = A.post_appreciation(self.animal.name, dry_run=0, s=self.settings())
		self.assertEqual(r["status"], "skipped")
		self.assertIn("minimum", r["reason"])
		self.assertEqual(self.value(), 120000)
		self.set_weight(410)  # worth 3,000 more
		r = A.post_appreciation(self.animal.name, dry_run=0, s=self.settings())
		self.assertEqual(r["status"], "posted")
		self.assertEqual(self.value(), 123000)

	def test_decrease_only_when_allowed(self):
		A.post_appreciation(self.animal.name, dry_run=0, s=self.settings())
		self.set_weight(300)
		r = A.post_appreciation(self.animal.name, dry_run=0, s=self.settings())
		self.assertEqual(r["status"], "skipped")
		self.assertIn("decreases", r["reason"])
		s = self.settings()
		s.appreciation_allow_decrease = 1
		r = A.post_appreciation(self.animal.name, dry_run=0, s=s)
		self.assertEqual(r["status"], "posted", r)
		self.assertEqual(self.value(), 90000)

	def test_cap_and_stop_at_first_calving(self):
		s = self.settings(max_value=50000)
		self.assertEqual(A.post_appreciation(self.animal.name, dry_run=1, s=s)["new_value"], 50000)
		s = self.settings(stop_at_first_calving=1)
		frappe.db.set_value("Animal", self.animal.name, "parity", 1, update_modified=False)
		frappe.db.set_value("Animal", self.animal.name, "last_calving_date", frappe.utils.today(), update_modified=False)
		s.get(A.MATRIX)[0].band = "Cow"
		r = A.post_appreciation(self.animal.name, dry_run=1, s=s)
		self.assertEqual(r["status"], "skipped")
		self.assertTrue(r["stopped"])

	def test_sold_asset_is_never_touched(self):
		frappe.db.set_value("Asset", self.asset, {"status": "Sold", "disposal_date": frappe.utils.today()})
		r = A.post_appreciation(self.animal.name, dry_run=0, s=self.settings())
		self.assertEqual(r["status"], "skipped")
		self.assertFalse(frappe.db.exists("Asset Value Adjustment", {"asset": self.asset}))
		frappe.db.set_value("Asset", self.asset, {"status": "Submitted", "disposal_date": None})
		frappe.db.set_value("Animal", self.animal.name, "status", "Sold")
		r = A.post_appreciation(self.animal.name, dry_run=0, s=self.settings())
		self.assertEqual(r["status"], "skipped")
		self.assertFalse(frappe.db.exists("Asset Value Adjustment", {"asset": self.asset}))

	def test_switched_off_or_no_account_does_not_post(self):
		s = self.settings()
		s.appreciation_enabled = 0
		self.assertEqual(A.post_appreciation(self.animal.name, dry_run=0, s=s)["status"], "skipped")
		s = self.settings()
		s.appreciation_account = None
		self.assertEqual(A.post_appreciation(self.animal.name, dry_run=0, s=s)["status"], "skipped")
		self.assertFalse(frappe.db.exists("Asset Value Adjustment", {"asset": self.asset}))

	def test_history_and_current_value(self):
		r = A.post_appreciation(self.animal.name, dry_run=0, s=self.settings())
		h = A.value_history(self.animal.name)
		self.assertEqual(h["asset"], self.asset)
		self.assertEqual(h["current_value"], 120000)
		self.assertEqual(h["events"][0]["ref"], r["adjustment"])
		self.assertEqual(h["events"][0]["amount"], 115000)
		cv = A.current_value(self.animal.name)
		self.assertEqual((cv["source"], cv["value"]), ("asset", 120000))
