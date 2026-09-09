import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common.events import new_livestock_event


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _operator():
	name = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	if not name:
		raise AssertionError("kaitet.local has no active Employee to attribute events to")
	return name


class TestNewLivestockEventStamps(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(_set_window, 0)
		_set_window(1)
		self.operator = _operator()

	def test_a_past_date_is_stamped(self):
		past = add_days(today(), -45)
		doc = new_livestock_event(
			{"event_date": past, "operator": self.operator}, "Deworming"
		)
		self.assertEqual(doc.custom_is_backdated, 1)
		self.assertEqual(str(doc.event_date), past)

	def test_today_is_not_stamped(self):
		doc = new_livestock_event({"operator": self.operator}, "Deworming")
		self.assertEqual(doc.custom_is_backdated, 0)

	def test_the_type_specific_date_also_stamps(self):
		"""A form that sends only service_date must still be recognised as
		backdated — event_date is derived from it, so the two must agree."""
		past = add_days(today(), -60)
		doc = new_livestock_event(
			{"service_date": past, "operator": self.operator}, "Service", date_key="service_date"
		)
		self.assertEqual(doc.custom_is_backdated, 1)
		self.assertEqual(str(doc.event_date), past)

	def test_a_backdated_build_is_refused_when_the_window_is_closed(self):
		_set_window(0)
		with self.assertRaises(frappe.ValidationError) as caught:
			new_livestock_event(
				{"event_date": add_days(today(), -5), "operator": self.operator}, "Deworming"
			)
		self.assertIn("Backdating is closed", str(caught.exception))

	def test_a_live_build_is_unaffected_when_the_window_is_closed(self):
		_set_window(0)
		doc = new_livestock_event({"operator": self.operator}, "Deworming")
		self.assertEqual(doc.custom_is_backdated, 0)
