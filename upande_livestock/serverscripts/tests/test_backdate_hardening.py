# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""`custom_is_backdated` is a claim, and a claim gets checked.

The field is `read_only`, which is a desk affordance and nothing more. A user
with create rights can POST

    /api/resource/Livestock Event
    {"event_date": <today>, "custom_is_backdated": 1, ...}

and, before this, collect both privileges the flag carries:

  * `guards.check_guards` returns early for a flagged doc while the window is
    open — so the age, interval and duplicate rules are skipped on an event
    that is not historical at all;
  * `LivestockEvent.post_stock_issue` asks `backdate.suppresses_stock`, which
    looks at the flag and NOT at the window — so the drug or semen Material
    Issue is skipped whatever the switch says.

`validate` now clears a flag the document's own date does not support. It never
*sets* one: the spec's rule is that the flag is stored, not derived, because
`event_date < creation` would also catch an honest late entry typed the next
morning, and those must stay distinguishable from a deliberate history load.
Clearing a false claim is not deriving a true one.

The forward-date half is a separate rule with a separate reason. `resolve`
deliberately does not call tomorrow "backdated", so a future date passed through
unstamped, unguarded and — on the feeding path — posting real Stock Entries on a
day that has not happened. Every mobile `DateField` already caps at today and
the desk pickers now carry `max`; this is the same rule for REST, which has no
picker.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, flt, today


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _an_animal():
	tag = frappe.generate_hash(length=10)
	return frappe.get_doc(
		{
			"doctype": "Animal",
			"tag_number": tag,
			"burn_name": tag,
			"sex": "Female",
			"status": "Active",
			"date_of_birth": add_months(today(), -36),
		}
	).insert(ignore_permissions=True)


class TestClientSuppliedBackdatedFlag(IntegrationTestCase):
	"""The window is held OPEN throughout — that is the state in which a forged
	flag is worth something, and the state this farm is in during a history
	load."""

	def setUp(self):
		self.addCleanup(_set_window, 0)
		_set_window(1)
		self.animal = _an_animal()
		self.operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		self.addCleanup(frappe.db.rollback)

	def _event(self, event_date, backdated=1, **extra):
		return frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal.name,
				"event_type": "Deworming",
				"event_date": event_date,
				"operator": self.operator,
				"custom_is_backdated": backdated,
				**extra,
			}
		)

	def test_a_flag_on_todays_event_is_dropped(self):
		doc = self._event(today())
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.custom_is_backdated, 0)
		self.assertEqual(frappe.db.get_value("Livestock Event", doc.name, "custom_is_backdated"), 0)

	def test_a_forged_flag_does_not_buy_the_guard_exemption(self):
		"""The consequence, not just the field. Two dewormings two days apart
		break the minimum-interval rule; with the window open, the flag was the
		only thing standing between a client and switching that rule off for
		an event dated today."""
		anchor = self._event(add_days(today(), -2), backdated=0)
		anchor.insert(ignore_permissions=True)
		anchor.submit()
		with self.assertRaises(frappe.ValidationError):
			self._event(today()).insert(ignore_permissions=True)

	def test_a_genuinely_backdated_event_keeps_its_flag(self):
		"""The control. Sanitising must not disarm the feature it protects."""
		doc = self._event(add_days(today(), -30))
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.custom_is_backdated, 1)

	def test_an_unflagged_past_event_is_not_flagged_for_it(self):
		"""Stored, not derived: an honest late entry stays distinguishable from
		a deliberate history load, so validate must never SET the flag."""
		doc = self._event(add_days(today(), -30), backdated=0)
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.custom_is_backdated, 0)

	def test_a_future_event_date_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			self._event(add_days(today(), 3), backdated=0).insert(ignore_permissions=True)
		self.assertIn("cannot be in the future", str(caught.exception))


class TestForgedFlagDoesNotSuppressStock(IntegrationTestCase):
	"""`suppresses_stock` reads the flag and never the window, so a forged flag
	skipped the drug Material Issue on an event dated today — recording the
	consumption as data and leaving the store overstated, permanently, with
	nothing on the record to say a reconciliation was owed."""

	def setUp(self):
		self.addCleanup(_set_window, 0)
		_set_window(1)
		from upande_livestock.serverscripts.common import stock as livestock_stock

		self.warehouse = livestock_stock.drug_warehouse()
		row = frappe.db.sql(
			"""SELECT item_code FROM `tabBin`
			   WHERE warehouse = %s AND actual_qty > 10 LIMIT 1""",
			(self.warehouse,),
			as_dict=True,
		)
		if not row:
			self.skipTest("no drug stock on kaitet.local to test against")
		self.item = row[0].item_code
		self.animal = _an_animal()
		self.operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		self.addCleanup(frappe.db.rollback)

	def _bin_qty(self):
		return flt(
			frappe.db.get_value(
				"Bin", {"item_code": self.item, "warehouse": self.warehouse}, "actual_qty"
			)
		)

	def test_todays_drugs_still_leave_the_store_despite_the_flag(self):
		before = self._bin_qty()
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal.name,
				"event_type": "Deworming",
				"event_date": today(),
				"operator": self.operator,
				"custom_is_backdated": 1,
				"drug_issues": [
					{"item_code": self.item, "qty": 2, "source_warehouse": self.warehouse}
				],
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		doc.reload()
		self.assertEqual(doc.custom_is_backdated, 0)
		self.assertTrue(doc.stock_entry, "a live event must still post its Material Issue")
		self.assertEqual(self._bin_qty(), before - 2)


class TestTheOtherDoctypesSanitiseToo(IntegrationTestCase):
	"""The five other doctypes that carry the field.

	`validate()` is called directly rather than through `insert()`: these
	controllers' validate methods now consist of exactly the backdate checks
	(bar the weight record's own two rules), so this exercises the real code
	without dragging in each doctype's mandatory-field set — which would make
	the test about fixtures rather than about the flag.
	"""

	CASES = (
		("Livestock Disposal", "disposal_date", {"disposal_type": "Condemned"}),
		("Livestock Health Case", "opened_date", {}),
		("Livestock Diagnosis", "diagnosis_date", {}),
		("Livestock Weight Record", "weight_date", {"weight_kg": 400}),
		("Milk Recording", "recording_date", {"total_yield_kg": 10}),
	)

	def _doc(self, doctype, date_field, date, extra):
		doc = frappe.new_doc(doctype)
		doc.update(extra)
		doc.set(date_field, date)
		doc.custom_is_backdated = 1
		return doc

	def test_a_flag_on_todays_date_is_dropped(self):
		for doctype, date_field, extra in self.CASES:
			with self.subTest(doctype=doctype):
				doc = self._doc(doctype, date_field, today(), extra)
				doc.validate()
				self.assertEqual(doc.custom_is_backdated, 0)

	def test_a_flag_on_a_past_date_survives(self):
		for doctype, date_field, extra in self.CASES:
			with self.subTest(doctype=doctype):
				doc = self._doc(doctype, date_field, add_days(today(), -10), extra)
				doc.validate()
				self.assertEqual(doc.custom_is_backdated, 1)

	def test_a_future_date_is_refused(self):
		for doctype, date_field, extra in self.CASES:
			with self.subTest(doctype=doctype):
				doc = self._doc(doctype, date_field, add_days(today(), 5), extra)
				with self.assertRaises(frappe.ValidationError) as caught:
					doc.validate()
				self.assertIn("future", str(caught.exception))
