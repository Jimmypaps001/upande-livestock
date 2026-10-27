# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The animal's slaughter-safe date is the latest over her health cases."""

import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common import withdrawal


class TestSlaughterSafeDate(IntegrationTestCase):
	def _with(self, value):
		return patch.object(frappe.db, "sql", return_value=[(value,)])

	def test_the_latest_date_wins(self):
		with self._with(datetime.date(2026, 11, 3)):
			self.assertEqual(withdrawal.slaughter_safe_date("A1"), datetime.date(2026, 11, 3))

	def test_no_case_with_a_date_is_none(self):
		with self._with(None):
			self.assertIsNone(withdrawal.slaughter_safe_date("A1"))

	def test_no_animal_is_none_without_a_query(self):
		with patch.object(frappe.db, "sql") as sql:
			self.assertIsNone(withdrawal.slaughter_safe_date(None))
		sql.assert_not_called()

	def test_the_real_query_runs_on_this_site(self):
		self.assertIsNone(withdrawal.slaughter_safe_date("ZZ NO SUCH ANIMAL"))
