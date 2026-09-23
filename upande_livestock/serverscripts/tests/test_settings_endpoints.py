# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The two endpoints behind the Settings page.

Livestock Settings is a Single with fifty editable scalars and three child
tables. Until now nothing read it whole: the handset asked for one field at a
time through `frappe.client.get_single_value`, which is fine for the two or
three values a screen needs and absurd for a settings page.

What is worth testing here is not that a dict comes back. It is the two ways a
settings endpoint goes wrong:

* it writes whatever fieldname it is handed onto the Single, so `payload` picks
  the column instead of the caller, and
* it reads a permission it never checked, so anyone who can open the app can
  change how the whole farm behaves.

Both have a test below, and both were watched to fail against a naive
implementation before the real one was written.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.settings.livestock_settings import livestock_settings
from upande_livestock.serverscripts.settings.save_livestock_settings import save_livestock_settings

DOCTYPE = "Livestock Settings"
LAYOUT = {"Tab Break", "Section Break", "Column Break"}
TABLES = {"Table", "Table MultiSelect"}


def _scalar_fieldnames():
	"""Read off the doctype, never a hand-kept list — a field added to the
	DocType and forgotten by the endpoint is exactly what this catches."""
	return {
		df.fieldname
		for df in frappe.get_meta(DOCTYPE).fields
		if df.fieldtype not in LAYOUT and df.fieldtype not in TABLES
	}


class TestLivestockSettingsEndpoints(IntegrationTestCase):
	def test_the_read_endpoint_returns_every_scalar_field(self):
		result = livestock_settings()
		self.assertNotIn("error", result)

		laid_out = {
			field["fieldname"]
			for tab in result["tabs"]
			for section in tab["sections"]
			for field in section["fields"]
		}
		self.assertEqual(sorted(_scalar_fieldnames() - laid_out), [], "scalars the page would never show")
		self.assertEqual(
			sorted(_scalar_fieldnames() - set(result["values"])),
			[],
			"scalars with no value in the payload",
		)

	def test_the_read_endpoint_carries_the_child_table_rows(self):
		"""The grids are read-only on the page, which is only honest if the page
		can actually show what is in them."""
		result = livestock_settings()
		tables = {t["fieldname"]: t for t in result["tables"]}
		self.assertEqual(
			sorted(tables),
			[
				"bought_in_concentrates",
				"custom_company_cost_centers",
				"custom_drug_warehouses",
				"feed_source_warehouses",
				"growth_ladder",
			],
		)
		for table in tables.values():
			self.assertIn("rows", table)
			self.assertTrue(table["columns"], f"{table['fieldname']} has no columns to show")

	def test_an_unknown_fieldname_is_refused(self):
		"""A dict handed straight to set_value would write this. It must not."""
		before = frappe.db.sql(
			"select count(*) from `tabSingles` where doctype=%s and field=%s",
			(DOCTYPE, "not_a_real_setting"),
		)[0][0]
		result = save_livestock_settings({"not_a_real_setting": "anything"})
		self.assertIn("error", result)
		self.assertIn("not_a_real_setting", result["error"])
		after = frappe.db.sql(
			"select count(*) from `tabSingles` where doctype=%s and field=%s",
			(DOCTYPE, "not_a_real_setting"),
		)[0][0]
		self.assertEqual(before, after, "the unknown field was written anyway")

	def test_a_user_who_may_not_write_the_settings_is_refused(self):
		"""A farm worker can open the app. That must not be the same thing as
		being able to change the gestation period for the whole herd."""
		email = "settings-guard-test@example.com"
		if not frappe.db.exists("User", email):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Settings Guard",
					"send_welcome_email": 0,
				}
			)
			user.insert(ignore_permissions=True)
			user.add_roles("Livestock Attendant")

		frappe.set_user(email)
		try:
			result = save_livestock_settings({"heat_cycle_days": 22})
			self.assertIn("error", result)
			self.assertIn("not permitted", result["error"].lower())
		finally:
			frappe.set_user("Administrator")

		self.assertNotEqual(
			frappe.db.get_single_value(DOCTYPE, "heat_cycle_days"), 22, "the refusal did not hold"
		)

	def test_a_saved_value_round_trips(self):
		field = "min_hoof_trimming_interval_days"
		original = livestock_settings()["values"][field]
		try:
			result = save_livestock_settings({field: 91})
			self.assertNotIn("error", result)
			self.assertEqual(result["changed"][field]["to"], 91)
			self.assertEqual(livestock_settings()["values"][field], 91)
		finally:
			save_livestock_settings({field: original})
		self.assertEqual(livestock_settings()["values"][field], original)

	def test_a_zero_is_refused_where_zero_is_not_a_configuration(self):
		"""`repair_zeroed_age_interval_settings` exists because this already
		happened once: a stored 0 reads back as 'rule off'."""
		result = save_livestock_settings({"gestation_period_days": 0})
		self.assertIn("error", result)
		self.assertIn("0", result["error"])
		self.assertNotEqual(frappe.db.get_single_value(DOCTYPE, "gestation_period_days"), 0)

	def test_a_link_that_names_nothing_is_refused(self):
		"""These fields post stock and journal entries. A warehouse that does not
		exist is not a typo the operator finds out about later."""
		result = save_livestock_settings({"drug_warehouse": "No Such Warehouse - ZZ"})
		self.assertIn("error", result)
		self.assertIn("No Such Warehouse - ZZ", result["error"])
