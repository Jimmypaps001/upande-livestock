from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, now_datetime, to_timedelta, today
from erpnext.stock.utils import get_combine_datetime, get_stock_balance

from upande_livestock.serverscripts.feeding import _engine, feed_day_status


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _a_feedable_herd():
	for row in frappe.get_all("Herds", fields=["name", "bom", "number_of_animals"]):
		if row.bom and (row.number_of_animals or 0) > 0:
			info = _engine.get_herd_feeding_program(row.name)
			if info["can_manufacture"]:
				return row.name
	return None


class TestBackdatedFeeding(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(_set_window, 0)
		_set_window(1)
		self.herd = _a_feedable_herd()
		if not self.herd:
			self.skipTest("no herd on kaitet.local can currently be fed")
		# The bench test runner is Administrator, who has no Employee linked on
		# this site — _operator_or_throw would refuse every run below for that
		# reason alone, which is not what these tests are about. Resolve a real
		# Employee explicitly, the same way test_feeding_program.py does.
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not self.employee:
			self.skipTest("no active Employee on this site")

	def tearDown(self):
		_set_window(0)
		frappe.db.rollback()

	def test_a_run_dated_before_the_stock_existed_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			_engine.manufacture_herd_feed(
				self.herd, employee=self.employee, portion=0.1, posting_date=add_days(today(), -365)
			)
		self.assertIn("cannot post on", str(caught.exception))

	def test_a_refused_run_leaves_nothing_behind(self):
		"""The check has to run before the Work Order, not after — a half-built
		run reads as feed sitting in the store that is not there."""
		before = frappe.db.count("Work Order")
		try:
			_engine.manufacture_herd_feed(
				self.herd, employee=self.employee, portion=0.1, posting_date=add_days(today(), -365)
			)
		except frappe.ValidationError:
			pass
		self.assertEqual(frappe.db.count("Work Order"), before)

	def test_manufacture_and_issue_share_the_posting_date(self):
		res = _engine.manufacture_herd_feed(
			self.herd, employee=self.employee, portion=0.05, posting_date=today()
		)
		dates = {
			frappe.db.get_value("Stock Entry", res[key], "posting_date")
			for key in ("transfer_stock_entry", "manufacture_stock_entry", "issue_stock_entry")
		}
		self.assertEqual(len(dates), 1, "the three entries must land on one day")

	def test_the_feeding_event_carries_the_run_date_not_today(self):
		"""_record_feeding_event used to hardcode today(), which put every
		backdated run on the wrong day of the herd's timeline."""
		res = _engine.manufacture_herd_feed(
			self.herd, employee=self.employee, portion=0.05, posting_date=today()
		)
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(str(event.event_date), today())

	def test_a_system_run_is_labelled_system(self):
		res = _engine.manufacture_herd_feed(
			self.herd, employee=self.employee, portion=0.05, posting_date=today()
		)
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.custom_feed_mode, "System")

	def test_no_posting_date_still_works(self):
		"""Every existing caller passes nothing (but for an employee, since the
		bench test runner has none — see setUp). They must keep working."""
		res = _engine.manufacture_herd_feed(self.herd, employee=self.employee, portion=0.05)
		self.assertTrue(res["issue_stock_entry"])

	def test_a_backdated_run_the_ledger_covered_is_not_re_refused_by_todays_stock(self):
		"""A backdated run that the historical ledger covered must not then be
		refused by _run_manufacture's own check against today's Bin — that used
		to be exactly what happened: `manufacture_herd_feed` judged the run
		against the ledger as it stood on the posting date, and then
		`_run_manufacture` judged it again, unconditionally, against today's
		stock. Two different questions, and the second could refuse a run the
		first had already correctly allowed — defeating the feature's main
		case, a farm entering last month's feeding for stock since consumed.

		This cannot be pinned against real stock history on kaitet.local: every
		feedable herd's BOM was checked by hand (looking back 60 days, per
		line) and none has a line whose stock today is lower than it was on any
		earlier day in that window — this farm's stock only goes down between
		restocks, never up, in the period available. Fabricating the gap with
		backdated Stock Entries was rejected too: ERPNext can enqueue an async
		stock-repost job for a backdated write, which runs outside this test's
		transaction and could touch the real ledger even after rollback.

		So this pins the seam directly instead. `_assert_can_cover` (the live
		check) is forced to refuse unconditionally. The run is backdated to
		yesterday with the same small portion the other tests in this file use
		successfully for today — a quantity the real historical ledger
		certainly covers, since the underlying stock has not moved between
		yesterday and today for this herd. If the run still succeeds, the live
		check was never consulted for it, which is exactly what
		`already_verified=True` is for. If the old double-check bug were still
		there, this run would be refused by the stub below even though the
		real historical check, running for real, already passed it.
		"""

		def _refuse_unconditionally(*args, **kwargs):
			frappe.throw("today's stock cannot cover it (forced by test)")

		with mock.patch.object(_engine, "_assert_can_cover", side_effect=_refuse_unconditionally):
			res = _engine.manufacture_herd_feed(
				self.herd,
				employee=self.employee,
				portion=0.05,
				posting_date=add_days(today(), -1),
			)
		self.assertTrue(res["issue_stock_entry"])


class TestManufactureConcentrateStillChecksStock(IntegrationTestCase):
	"""`_run_manufacture`'s `already_verified` flag exists so a caller that has
	already judged a run does not get judged again — `manufacture_herd_feed`
	sets it. `manufacture_concentrate` passes no such flag and has no check of
	its own, so it depends entirely on `_run_manufacture`'s default. Pinned
	here because that default flipping the wrong way (`True`) is exactly what
	happened once already in this task: it silently switched off stock
	verification for concentrate manufacture, with nothing red to catch it."""

	def setUp(self):
		row = frappe.db.get_value(
			"Item", {"default_bom": ["is", "set"]}, ["name", "default_bom"], as_dict=True
		)
		if not row:
			self.skipTest("no item on kaitet.local has a default BOM")
		self.item_code = row.name

	def tearDown(self):
		frappe.db.rollback()

	def test_a_run_the_stores_cannot_cover_is_still_refused(self):
		"""A genuine shortfall, not a mocked one: a quantity nothing on this
		site stocks in that order of magnitude (the same technique
		test_feed_availability.py's test_today_matches_the_engine uses to force
		a real shortfall). If `already_verified` ever defaults to True again,
		this creates a Work Order and Stock Entries with no check at all,
		instead of raising."""
		before = frappe.db.count("Work Order")
		with self.assertRaises(frappe.ValidationError) as caught:
			_engine.manufacture_concentrate(self.item_code, qty=10**9)
		self.assertIn("Not enough stock", str(caught.exception))
		self.assertEqual(frappe.db.count("Work Order"), before)


class TestBackdatedFeedingNeedsTheWindow(IntegrationTestCase):
	"""Feeding was the one backdated write the window did not gate.

	Every other backdated path calls `backdate.assert_allowed`, so with the
	switch off — the default — a weight record dated last month is refused. No
	feeding path called it at all, so the same closed switch let `manual_feed`
	and `manufacture_feed` post a Work Order and four Stock Entries against a
	month-old date. Feeding is the one backdated write that still MOVES stock,
	which makes it the last one that should have been ungated.

	The window is forced CLOSED here — the opposite of TestBackdatedFeeding
	above, which opens it.
	"""

	def setUp(self):
		self.addCleanup(_set_window, 0)
		_set_window(0)
		self.herd = _a_feedable_herd()
		if not self.herd:
			self.skipTest("no herd on kaitet.local can currently be fed")
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not self.employee:
			self.skipTest("no active Employee on this site")
		self.addCleanup(frappe.db.rollback)

	def test_a_backdated_run_is_refused_while_the_window_is_closed(self):
		before = frappe.db.count("Work Order")
		with self.assertRaises(frappe.ValidationError) as caught:
			_engine.manufacture_herd_feed(
				self.herd, employee=self.employee, portion=0.05, posting_date=add_days(today(), -1)
			)
		self.assertIn("Backdating is closed", str(caught.exception))
		self.assertEqual(frappe.db.count("Work Order"), before, "nothing may post behind the refusal")

	def test_a_backdated_issue_is_refused_too(self):
		"""feed_herd is the other door into a dated Stock Entry."""
		with self.assertRaises(frappe.ValidationError) as caught:
			_engine.feed_herd(self.herd, 1, employee=self.employee, posting_date=add_days(today(), -1))
		self.assertIn("Backdating is closed", str(caught.exception))

	def test_todays_run_is_untouched_by_the_closed_window(self):
		"""The control. A closed window must not stop normal feeding — that is
		the whole distinction between a gate and an outage."""
		res = _engine.manufacture_herd_feed(
			self.herd, employee=self.employee, portion=0.05, posting_date=today()
		)
		self.assertTrue(res["issue_stock_entry"])

	def test_a_future_dated_run_is_refused_whatever_the_window_says(self):
		"""backdate.resolve deliberately does not call a forward date backdated,
		so the window would never have caught this one. A feed run dated
		tomorrow posted real Stock Entries on a day that has not happened."""
		for window in (0, 1):
			with self.subTest(window=window):
				_set_window(window)
				with self.assertRaises(frappe.ValidationError) as caught:
					_engine.manufacture_herd_feed(
						self.herd,
						employee=self.employee,
						portion=0.05,
						posting_date=add_days(today(), 1),
					)
				self.assertIn("cannot be in the future", str(caught.exception))


class TestSameDayBackdatedStagger(IntegrationTestCase):
	"""Two backdated feed runs for one herd on one date used to both price and
	post at the same instant (FEED_RUN_TIME, for both) — so the second never
	saw the first's consumption in the ledger. It read the same stale balance
	the first run had already reduced, passed a check it should have failed,
	and only found out at ERPNext's own NegativeStockError, after a Work
	Order and a transfer already existed. See `_engine._run_posting_time` and
	`feed_day_status.runs_already_posted`.

	The day used throughout is `today() - 3`, not `-1`: a herd may genuinely
	already have real feed history from yesterday, but a run count is read
	fresh here (via `runs_already_posted`) rather than assumed to be zero, so
	whatever this farm's real ledger already holds for that day does not
	matter to any assertion below.
	"""

	def setUp(self):
		self.addCleanup(_set_window, 0)
		_set_window(1)
		self.herd = _a_feedable_herd()
		if not self.herd:
			self.skipTest("no herd on kaitet.local can currently be fed")
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not self.employee:
			self.skipTest("no active Employee on this site")
		self.addCleanup(frappe.db.rollback)
		self.day = add_days(today(), -3)
		_herd_doc, bom, _heads = _engine._herd_bom(self.herd)
		self.ration_item = bom.item
		# Read fresh rather than assumed: whatever this farm's ledger already
		# holds for this herd on this day, the two runs below must slot in
		# after it, not before it.
		self.runs_before = feed_day_status.runs_already_posted(
			self.ration_item, self.herd, self.day
		)
		self.expected_first_time = _engine._run_posting_time(self.runs_before)
		self.expected_second_time = _engine._run_posting_time(self.runs_before + 1)
		self.assertNotEqual(
			self.expected_first_time,
			self.expected_second_time,
			"the two slots must differ for this test to mean anything",
		)

	def test_a_second_backdated_run_sees_the_first_runs_consumption(self):
		first = _engine.manufacture_herd_feed(
			self.herd, employee=self.employee, portion=0.05, posting_date=self.day
		)
		first_time = frappe.db.get_value(
			"Stock Entry", first["transfer_stock_entry"], "posting_time"
		)
		self.assertEqual(first_time, to_timedelta(self.expected_first_time))

		transfer = frappe.get_doc("Stock Entry", first["transfer_stock_entry"])
		row = transfer.items[0]
		consumed_item, consumed_wh, consumed_qty = row.item_code, row.s_warehouse, flt(row.qty)

		# The balance before ANY of today's test writes touched this day —
		# this is exactly what the original bug's check kept reading no
		# matter how many runs had already gone out that day.
		start_of_day = flt(get_stock_balance(consumed_item, consumed_wh, self.day, "00:00:00"))

		# What the SECOND run's availability check must read: its own, later
		# instant, by which the first run's transfer has already posted.
		seen_by_second_check = flt(
			get_stock_balance(consumed_item, consumed_wh, self.day, self.expected_second_time)
		)
		self.assertAlmostEqual(seen_by_second_check, start_of_day - consumed_qty, places=4)

		second = _engine.manufacture_herd_feed(
			self.herd, employee=self.employee, portion=0.05, posting_date=self.day
		)
		second_time = frappe.db.get_value(
			"Stock Entry", second["transfer_stock_entry"], "posting_time"
		)
		self.assertEqual(second_time, to_timedelta(self.expected_second_time))

	def test_the_two_runs_stock_entries_have_strictly_increasing_posting_datetime(self):
		first = _engine.manufacture_herd_feed(
			self.herd, employee=self.employee, portion=0.05, posting_date=self.day
		)
		second = _engine.manufacture_herd_feed(
			self.herd, employee=self.employee, portion=0.05, posting_date=self.day
		)
		for key in ("transfer_stock_entry", "manufacture_stock_entry", "issue_stock_entry"):
			first_doc = frappe.db.get_value("Stock Entry", first[key], ["posting_date", "posting_time"])
			second_doc = frappe.db.get_value("Stock Entry", second[key], ["posting_date", "posting_time"])
			first_dt = get_combine_datetime(first_doc[0], first_doc[1])
			second_dt = get_combine_datetime(second_doc[0], second_doc[1])
			self.assertLess(first_dt, second_dt, f"{key} must post strictly after the first run's")

	def test_a_second_run_the_store_genuinely_cannot_cover_is_refused_by_our_check(self):
		"""Refused by `_availability.assert_can_cover_on` before anything posts —
		not by ERPNext's NegativeStockError, which would only fire after a Work
		Order and a transfer already existed. That distinction is the whole
		point of the pre-flight check."""
		_engine.manufacture_herd_feed(
			self.herd, employee=self.employee, portion=0.05, posting_date=self.day
		)
		before_wo = frappe.db.count("Work Order")
		before_se = frappe.db.count("Stock Entry")
		with self.assertRaises(frappe.ValidationError) as caught:
			_engine.manufacture_herd_feed(
				self.herd,
				employee=self.employee,
				heads=10**9,
				portion=1.0,
				posting_date=self.day,
			)
		message = str(caught.exception)
		self.assertIn("cannot post on", message)
		self.assertIn("Nothing was posted", message)
		self.assertNotIn("NegativeStockError", message)
		self.assertEqual(frappe.db.count("Work Order"), before_wo, "our check must run before any Work Order")
		self.assertEqual(frappe.db.count("Stock Entry"), before_se, "our check must run before any Stock Entry")

	def test_a_run_dated_today_still_stamps_the_current_clock_time(self):
		"""Only backdated runs are staggered — see `_is_backdated`. A run dated
		today must keep stamping the real clock time, not a computed slot."""
		just_before = now_datetime()
		res = _engine.manufacture_herd_feed(
			self.herd, employee=self.employee, portion=0.05, posting_date=today()
		)
		just_after = now_datetime()
		posting_date, posting_time = frappe.db.get_value(
			"Stock Entry", res["issue_stock_entry"], ["posting_date", "posting_time"]
		)
		posted_dt = get_combine_datetime(posting_date, posting_time)
		self.assertTrue(
			just_before <= posted_dt <= just_after,
			f"expected {posted_dt} between {just_before} and {just_after}",
		)
