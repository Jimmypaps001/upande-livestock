# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Overdue weighing: interval plus grace, both read from Livestock Settings."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common.weighing import weighing_due
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, submit_weight


def _due(animal):
	return next((r for r in weighing_due() if r["animal"] == animal), None)


class TestWeighingDue(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		frappe.db.set_single_value("Livestock Settings", "weighing_interval_days", 30)
		frappe.db.set_single_value("Livestock Settings", "weighing_grace_days", 5)
		self.herd = make_herd("ZZ Weigh", "Fattening", 0, 0).name

	def test_overdue_after_interval_plus_grace(self):
		late, ok = make_animal(self.herd), make_animal(self.herd)
		submit_weight(late.name, 300, days_ago=36)
		submit_weight(ok.name, 300, days_ago=35)
		row = _due(late.name)
		self.assertEqual((row["days_since"], row["overdue_by"]), (36, 1))
		self.assertEqual(row["last_weight_date"], frappe.utils.getdate(add_days(today(), -36)))
		self.assertIsNone(_due(ok.name))

	def test_never_weighed_counts_from_herd_entry(self):
		old, new = make_animal(self.herd), make_animal(self.herd)
		frappe.db.set_value("Animal", old.name, "acquisition_date", add_days(today(), -40))
		row = _due(old.name)
		self.assertEqual((row["days_since"], row["last_weight_date"]), (40, None))
		self.assertIsNone(_due(new.name))

	def test_zero_grace_honoured(self):
		frappe.db.set_single_value("Livestock Settings", "weighing_grace_days", 0)
		animal = make_animal(self.herd)
		submit_weight(animal.name, 300, days_ago=31)
		self.assertEqual(_due(animal.name)["overdue_by"], 1)

	def test_herd_without_weigh_monthly_ignored(self):
		frappe.db.set_value("Herds", self.herd, "weigh_monthly", 0)
		animal = make_animal(self.herd)
		frappe.db.set_value("Animal", animal.name, "acquisition_date", add_days(today(), -90))
		self.assertIsNone(_due(animal.name))
