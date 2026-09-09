import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import backdate


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


class TestBackdateResolve(IntegrationTestCase):
	def test_explicit_event_date_wins(self):
		past = add_days(today(), -30)
		date, is_back = backdate.resolve({"event_date": past, "service_date": today()}, "service_date")
		self.assertEqual(str(date), past)
		self.assertTrue(is_back)

	def test_the_type_specific_date_is_used_when_there_is_no_event_date(self):
		past = add_days(today(), -10)
		date, is_back = backdate.resolve({"service_date": past}, "service_date")
		self.assertEqual(str(date), past)
		self.assertTrue(is_back)

	def test_no_date_at_all_means_today_and_not_backdated(self):
		date, is_back = backdate.resolve({}, "service_date")
		self.assertEqual(str(date), today())
		self.assertFalse(is_back)

	def test_todays_date_is_not_backdated(self):
		_, is_back = backdate.resolve({"event_date": today()}, None)
		self.assertFalse(is_back)

	def test_a_future_date_is_not_backdated(self):
		"""Forward-dating is a different problem with different rules. This
		module answers one question and must not quietly own that one too."""
		_, is_back = backdate.resolve({"event_date": add_days(today(), 5)}, None)
		self.assertFalse(is_back)

	def test_an_empty_string_date_falls_through_to_today(self):
		"""A form that clears its date field posts "", not a missing key."""
		date, is_back = backdate.resolve({"event_date": "", "service_date": ""}, "service_date")
		self.assertEqual(str(date), today())
		self.assertFalse(is_back)


class TestBackdateWindow(IntegrationTestCase):
	def tearDown(self):
		_set_window(0)

	def test_window_reads_the_setting(self):
		_set_window(1)
		self.assertTrue(backdate.window_open())
		_set_window(0)
		self.assertFalse(backdate.window_open())

	def test_assert_allowed_passes_when_open(self):
		_set_window(1)
		backdate.assert_allowed(True)  # must not throw

	def test_assert_allowed_refuses_a_backdated_record_when_closed(self):
		_set_window(0)
		with self.assertRaises(frappe.ValidationError) as caught:
			backdate.assert_allowed(True)
		self.assertIn("Backdating is closed", str(caught.exception))

	def test_assert_allowed_ignores_a_live_record_when_closed(self):
		_set_window(0)
		backdate.assert_allowed(False)  # must not throw


class TestBackdateStock(IntegrationTestCase):
	def test_feeding_still_moves_stock_when_backdated(self):
		"""Feeding is the single exception. It is the whole reason the rule is
		expressed as a function rather than a constant."""
		self.assertFalse(backdate.suppresses_stock("Feeding", True))

	def test_other_types_do_not_move_stock_when_backdated(self):
		for event_type in ("Deworming", "Vaccination", "Service"):
			with self.subTest(event_type=event_type):
				self.assertTrue(backdate.suppresses_stock(event_type, True))

	def test_nothing_is_suppressed_for_a_live_record(self):
		self.assertFalse(backdate.suppresses_stock("Deworming", False))

	def test_a_document_can_be_passed_instead_of_a_type(self):
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Deworming"
		self.assertTrue(backdate.suppresses_stock(doc, True))


class TestBackdateStamp(IntegrationTestCase):
	def test_stamp_sets_the_flag(self):
		doc = frappe.new_doc("Livestock Event")
		backdate.stamp(doc, True)
		self.assertEqual(doc.custom_is_backdated, 1)

	def test_stamp_clears_the_flag_for_a_live_record(self):
		doc = frappe.new_doc("Livestock Event")
		doc.custom_is_backdated = 1
		backdate.stamp(doc, False)
		self.assertEqual(doc.custom_is_backdated, 0)

	def test_stamp_is_silent_on_a_doctype_without_the_field(self):
		"""Called from shared helpers that also build documents which will never
		carry the field. A missing field is not an error."""
		doc = frappe.new_doc("Livestock Alert")
		backdate.stamp(doc, True)  # must not throw
