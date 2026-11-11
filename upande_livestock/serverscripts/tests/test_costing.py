# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Cost per animal on a site: the labour book, who may see it, and the report's shape.

The arithmetic is tested without a site in `costing/test_maths.py`; this asks
the questions only a site can answer — the doctype's own validation, the
guards, and that the report reads the ledger without falling over when
upande_production is absent.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common.envelope import NUTRITIONIST_ROLE
from upande_livestock.serverscripts.costing import _data, _production
from upande_livestock.serverscripts.costing.cost_per_animal import cost_per_animal
from upande_livestock.serverscripts.costing.daily_labour import daily_labour
from upande_livestock.serverscripts.costing.save_daily_labour import save_daily_labour
from upande_livestock.serverscripts.tests.test_employee_gate import _drop_all, _user

#: A day far enough back that no real labour entry is on it.
DAY = "2001-01-02"


class TestCosting(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete(_data.LABOUR_DOCTYPE, {"labour_date": DAY})
		self.addCleanup(_drop_all)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete(_data.LABOUR_DOCTYPE, {"labour_date": DAY})

	def test_a_day_is_one_record_and_takes_the_default_rate(self):
		rates = _data.default_rates()
		out = save_daily_labour({"date": DAY, "rows": [{"category": "Feedlot workers", "workers": 6}]})
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(out["total_amount"], 6 * rates["Feedlot workers"])
		# Saving the day again replaces it, never a second record counted twice.
		again = save_daily_labour({"date": DAY, "rows": [{"category": "Herders", "workers": 2, "day_rate": 500}]})
		self.assertTrue(again.get("ok"), again)
		self.assertEqual(frappe.db.count(_data.LABOUR_DOCTYPE, {"labour_date": DAY}), 1)
		self.assertEqual(again["total_amount"], 1000)
		self.assertEqual(_data.labour_by_day(DAY, DAY), {frappe.utils.getdate(DAY): 1000})

	def test_tomorrow_and_unknown_categories_are_refused(self):
		self.assertIn("error", save_daily_labour({"date": add_days(today(), 1), "rows": []}))
		self.assertIn("error", save_daily_labour({"date": DAY, "rows": [{"category": "Cooks", "workers": 1}]}))

	def test_an_unentered_day_offers_every_category_at_its_rate(self):
		out = daily_labour(DAY)
		self.assertTrue(out.get("ok"), out)
		self.assertFalse(out["saved"])
		self.assertEqual([r["category"] for r in out["rows"]], ["Feedlot workers", "Herders", "Other"])

	def test_the_report_without_production(self):
		with patch.object(_production, "installed", return_value=False):
			out = cost_per_animal(add_days(today(), -6), today())
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(len(out["days"]), 7)
		self.assertFalse(out["fuel_available"])
		self.assertIsNone(out["silage"])
		for row in out["days"]:
			self.assertEqual(row["fuel_cost"], 0)

	def test_a_missing_production_api_is_not_a_failure(self):
		with patch.object(_production, "installed", return_value=True), \
			patch.object(frappe, "get_attr", side_effect=AttributeError("gone")):
			fuel = _production.fuel(today(), today(), ["Anything"])
		self.assertFalse(fuel["available"])
		self.assertTrue(fuel["reason"])

	def test_the_nutritionist_sees_no_costs(self):
		email = _user(NUTRITIONIST_ROLE)
		frappe.db.commit()
		frappe.set_user(email)
		self.assertIn("error", cost_per_animal(today(), today()))
		self.assertIn("error", save_daily_labour({"date": DAY, "rows": []}))

	def test_only_the_manager_writes_labour(self):
		email = _user("Livestock Attendant")
		frappe.db.commit()
		frappe.set_user(email)
		self.assertTrue(daily_labour(DAY).get("ok"))
		self.assertIn("error", save_daily_labour({"date": DAY, "rows": [{"category": "Herders", "workers": 1}]}))
