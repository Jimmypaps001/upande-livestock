# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The patch runs. That is the whole point of this file.

It did not. It took the production migrate down on kaitetv16.nbg.frappe.cloud:

    frappe.db.has_column("tabSingles", "value")
    MySQLdb.ProgrammingError: ('DocType', 'tabSingles')

`has_column(doctype, column)` prefixes `tab` ITSELF (database.py: `get_table_
columns` does `"tab" + doctype`), so passing a table name asks for
`tabtabSingles`. The line was a "sanity" guard on a core Frappe table that
always exists — it protected nothing and broke everything.

AND IT WAS HIDING A SECOND ONE. With the guard removed, the next line fails too:

    frappe.db.get_value("Singles", {...}, "value")
    OperationalError (1054): Unknown column 'creation' in 'ORDER BY'

`tabSingles` is a pseudo-doctype with no `creation`, so the ORM's default
ordering breaks against it. `patches/repair_zeroed_age_interval_settings`
already knew this and says so in `_raw`'s docstring; this patch should have
matched it and did not.

WHY NOBODY SAW IT. Every local migrate in the session that wrote this patch was
run with `--skip-failing`, which swallows the traceback AND still writes the
Patch Log row — so the patch looked applied here while having failed. These
tests call the functions directly, so no flag can hide them.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches import one_cost_centre_per_herd as P


class TestThePatchActuallyRuns(IntegrationTestCase):
	def test_carrying_the_flat_setting_over_does_not_raise(self):
		"""The exact call that took production down."""
		P.carry_the_flat_setting_into_a_company_row()

	def test_carrying_the_herd_field_across_does_not_raise(self):
		P.carry_the_herds_custom_field_across()

	def test_the_whole_patch_runs(self):
		P.execute()

	def test_it_runs_twice(self):
		"""A patch that failed once is re-run by the next migrate, so the second
		run has to be as safe as the first."""
		P.execute()
		P.execute()


class TestReadingTheFlatSetting(IntegrationTestCase):
	def test_it_reads_tabsingles_without_the_orm(self):
		"""Raw SQL, matching `repair_zeroed_age_interval_settings._raw`: the ORM
		orders by `creation` and `tabSingles` has no such column."""
		self.assertIsNone(P._flat_cost_centre("a field no site has ever had"))

	def test_it_finds_a_value_that_is_there(self):
		frappe.db.sql(
			"delete from `tabSingles` where doctype=%s and field=%s",
			(P.SETTINGS, "custom_test_probe"),
		)
		frappe.db.sql(
			"insert into `tabSingles` (doctype, field, `value`) values (%s, %s, %s)",
			(P.SETTINGS, "custom_test_probe", "Probe - KR"),
		)
		try:
			self.assertEqual(P._flat_cost_centre("custom_test_probe"), "Probe - KR")
		finally:
			frappe.db.sql(
				"delete from `tabSingles` where doctype=%s and field=%s",
				(P.SETTINGS, "custom_test_probe"),
			)
