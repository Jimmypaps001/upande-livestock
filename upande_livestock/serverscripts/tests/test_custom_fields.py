"""The custom fields this app puts on doctypes it does not own.

Work Order, BOM and Stock Entry belong to ERPNext and are shared with three
other installed apps, so nothing this app adds to them may be assumed to exist
and nothing it adds may get in anyone else's way.

WHY DECLARED RATHER THAN EXPORTED. A fixture only restores what was last
exported from some site's database, so a field that was never exported is a
field that exists nowhere else. That is exactly how `Work Order.custom_herd`
came to be made by hand here on 2026-07-14, read by `ration_history` in SQL,
and missing on the live site — where the Rations page died with

    OperationalError (1054): Unknown column 'wo.custom_herd' in 'SELECT'

`upande_scp/serverscripts/store/stock_entry_fields.py` reached this conclusion
first and its docstring says so; this is the same pattern.

AND OUT OF EVERYONE ELSE'S WAY. `40ee471` shipped the two Work Order fields with
no tab and no `depends_on`, so they appeared on every Work Order on the site,
spray orders included. BOM already had the right answer — a Tab Break gated on
`custom_is_livestock_feed`, with the livestock fields inside it. Work Order gets
the same, gated on the same fact fetched from the BOM rather than on the herd,
because a concentrate run has no herd and its Work Order is still ours.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import test_custom_fields as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import json
import pathlib
import unittest

import frappe

from upande_livestock.serverscripts.common import custom_fields as CF


class TestTheDeclarationCoversWhatTheCodeReads(unittest.TestCase):
	def test_the_work_order_fields_the_rations_page_needs_are_declared(self):
		declared = {f["fieldname"] for f in CF.field_spec()["Work Order"]}
		self.assertIn("custom_herd", declared)
		self.assertIn("custom_no_of_cows", declared)

	def test_the_bom_fields_are_declared(self):
		declared = {f["fieldname"] for f in CF.field_spec()["BOM"]}
		self.assertEqual(
			declared,
			{"custom_livestock_tab", "custom_herd", "custom_is_livestock_feed", "custom_ration_kind"},
		)

	def test_the_milking_stock_entry_fields_are_declared(self):
		declared = {f["fieldname"] for f in CF.field_spec()["Stock Entry"]}
		self.assertEqual(
			declared,
			{
				"custom_milking_details_section",
				"custom_milking_time",
				"custom_cows_milked",
				"custom_milking_end_section",
			},
		)

	def test_every_declared_field_is_stamped_as_ours(self):
		"""Reconciliation deletes app-owned fields that leave the spec, so a
		field with no module stamp can never be cleaned up — and a field
		stamped as ours that belongs to SCP would be deleted from under them."""
		for doctype, fields in CF.field_spec().items():
			for f in fields:
				self.assertEqual(f.get("module"), CF.MODULE, f"{doctype}.{f['fieldname']}")


class TestTheWorkOrderTabKeepsUsOutOfTheWay(unittest.TestCase):
	def _wo(self):
		return {f["fieldname"]: f for f in CF.field_spec()["Work Order"]}

	def test_there_is_a_livestock_tab(self):
		self.assertEqual(self._wo()["custom_livestock_tab"]["fieldtype"], "Tab Break")

	def test_the_tab_only_shows_on_a_livestock_work_order(self):
		"""Otherwise every spray order on the site grows a Herd field."""
		self.assertEqual(
			self._wo()["custom_livestock_tab"]["depends_on"],
			"eval:doc.custom_is_livestock_feed",
		)

	def test_the_flag_is_fetched_from_the_bom_not_typed(self):
		flag = self._wo()["custom_is_livestock_feed"]
		self.assertEqual(flag["fieldtype"], "Check")
		self.assertEqual(flag["fetch_from"], "bom_no.custom_is_livestock_feed")
		self.assertTrue(flag["read_only"], "nobody types this; the BOM decides")

	def test_it_is_not_gated_on_the_herd(self):
		"""A concentrate run has no herd and is still a livestock work order.
		Gating the tab on the herd would hide the concentrate's own fields."""
		self.assertNotIn("custom_herd", self._wo()["custom_livestock_tab"]["depends_on"])

	def test_both_fields_sit_inside_the_tab(self):
		wo = self._wo()
		self.assertEqual(wo["custom_herd"]["insert_after"], "custom_is_livestock_feed")
		self.assertEqual(wo["custom_no_of_cows"]["insert_after"], "custom_herd")
		self.assertEqual(wo["custom_is_livestock_feed"]["insert_after"], "custom_livestock_tab")


class TestTheFieldsReallyLandOnTheSite(unittest.TestCase):
	"""The declaration is only true if `ensure` makes it true."""

	@classmethod
	def setUpClass(cls):
		CF.ensure_livestock_custom_fields()

	def test_work_order_has_the_tab_and_its_fields(self):
		meta = frappe.get_meta("Work Order")
		for fieldname in ("custom_livestock_tab", "custom_is_livestock_feed", "custom_herd", "custom_no_of_cows"):
			self.assertTrue(meta.has_field(fieldname), fieldname)

	def test_the_column_the_rations_page_selects_exists(self):
		self.assertTrue(frappe.db.has_column("Work Order", "custom_herd"))
		self.assertTrue(frappe.db.has_column("Work Order", "custom_no_of_cows"))

	def test_the_tab_is_gated_on_the_built_meta_too(self):
		f = frappe.get_meta("Work Order").get_field("custom_livestock_tab")
		self.assertEqual(f.depends_on, "eval:doc.custom_is_livestock_feed")

	def test_running_it_twice_changes_nothing(self):
		before = frappe.get_all("Custom Field", filters={"dt": "Work Order", "module": CF.MODULE}, pluck="name")
		CF.ensure_livestock_custom_fields()
		after = frappe.get_all("Custom Field", filters={"dt": "Work Order", "module": CF.MODULE}, pluck="name")
		self.assertEqual(sorted(before), sorted(after))


class TestTheFixtureNoLongerShipsThem(unittest.TestCase):
	def test_the_custom_field_fixture_is_withdrawn(self):
		"""Two owners for one field means the loser silently wins on migrate."""
		path = pathlib.Path(frappe.get_app_path("upande_livestock", "fixtures", "custom_field.json"))
		if not path.exists():
			return
		declared = {(dt, f["fieldname"]) for dt, fs in CF.field_spec().items() for f in fs}
		clash = [
			f"{r['dt']}-{r['fieldname']}"
			for r in json.loads(path.read_text())
			if (r["dt"], r["fieldname"]) in declared
		]
		self.assertEqual(clash, [], "declared in code AND shipped as a fixture")
