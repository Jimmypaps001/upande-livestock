import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.feeding import _engine


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
