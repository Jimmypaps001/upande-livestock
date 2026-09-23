"""Charging livestock stock movements to a cost centre that exists.

ERPNext refuses a Stock Entry outright — "Cost Center is mandatory for Item
{0}" — when the item's expense account is a profit-and-loss one and no cost
centre can be found. It looks in exactly two places: the Item Default for that
company, then the Company's own default.

On live, neither is set for dairy. Karen Roses, which the feed engine posts
under, has a blank default cost centre; 134 Dairy Feed items, 219 Dairy Drugs
and 429 Dairy Others carry no buying cost centre; and the Item Default rows
that exist for the feed meals are against other companies with the cost centre
empty. Six of the eight feed runs that failed in the week to 2026-09-21 died
there, naming `Dry Cows  Meal`.

These tests pin the fallback order and, more importantly, the two refusals: a
row that already has a cost centre is never rewritten, and nothing is invented
when there is no answer — a wrong cost centre is a real accounting error,
quieter and worse than the refusal it replaces.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import test_cost_center as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import cost_center as CC


class Row(dict):
	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError as e:
			raise AttributeError(k) from e

	def __setattr__(self, k, v):
		self[k] = v


class Doc:
	def __init__(self, rows, company=None):
		self._rows = rows
		self.company = company

	def get(self, key):
		return self._rows if key == "items" else None


class TestWhereTheCostCentreComesFrom(unittest.TestCase):
	def test_the_company_default_is_the_last_resort(self):
		"""A site that has configured its company properly needs no setting."""
		with patch.object(CC, "herd_cost_center", return_value=None), patch.object(
			CC, "setting_cost_center", return_value=None
		), patch.object(CC, "company_cost_center", return_value="Main - KR"):
			self.assertEqual(CC.resolve("Karen Roses"), "Main - KR")

	def test_nothing_anywhere_means_nothing(self):
		"""Not a guess. ERPNext's own refusal names the item; a wrong cost
		centre is a silent accounting error."""
		with patch.object(CC, "herd_cost_center", return_value=None), patch.object(
			CC, "setting_cost_center", return_value=None
		), patch.object(CC, "company_cost_center", return_value=None):
			self.assertIsNone(CC.resolve("Karen Roses"))

	def test_a_site_that_has_not_migrated_falls_through_rather_than_raising(self):
		"""Reading a child table that does not exist yet raises, so a deploy
		landing before its migrate would take feeding down instead of behaving
		as it did the day before."""
		meta = frappe.get_meta(CC.SETTINGS)
		with patch.object(meta, "has_field", return_value=False), patch.object(
			frappe, "get_meta", return_value=meta
		), patch.object(
			frappe, "get_all", side_effect=AssertionError("the table must not be read")
		):
			self.assertEqual(CC.setting_cost_center("Karen Roses"), None)


class TestStampingTheRows(unittest.TestCase):
	def test_blank_rows_are_filled(self):
		rows = [Row(cost_center=""), Row(cost_center=None)]
		with patch.object(CC, "resolve_with_source", return_value=("Dairy - KR", "herd")):
			self.assertEqual(CC.stamp(Doc(rows, "Karen Roses")), 2)
		self.assertEqual([r["cost_center"] for r in rows], ["Dairy - KR"] * 2)

	def test_a_row_that_already_has_one_is_never_rewritten(self):
		"""Whether it came from an Item Default or a person, it was deliberate.
		This is a fallback, not a policy."""
		rows = [Row(cost_center="Chosen - KR")]
		with patch.object(CC, "resolve_with_source", return_value=("Dairy - KR", "herd")):
			self.assertEqual(CC.stamp(Doc(rows, "Karen Roses")), 0)
		self.assertEqual(rows[0]["cost_center"], "Chosen - KR")

	def test_no_cost_centre_available_changes_nothing(self):
		rows = [Row(cost_center="")]
		with patch.object(CC, "resolve_with_source", return_value=(None, None)):
			self.assertEqual(CC.stamp(Doc(rows, "Karen Roses")), 0)
		self.assertEqual(rows[0]["cost_center"], "")

	def test_a_document_with_no_rows_is_fine(self):
		with patch.object(CC, "resolve_with_source", return_value=("Dairy - KR", "herd")):
			self.assertEqual(CC.stamp(Doc([], "Karen Roses")), 0)

	def test_it_never_takes_the_run_down(self):
		"""A feed run must not be lost because this helper had a bad day."""
		rows = [Row(cost_center="")]
		with patch.object(CC, "resolve_with_source", side_effect=RuntimeError("boom")):
			self.assertEqual(CC.stamp(Doc(rows, "Karen Roses")), 0)
		self.assertEqual(rows[0]["cost_center"], "")

	def test_the_company_comes_off_the_document_when_not_given(self):
		rows = [Row(cost_center="")]
		seen = {}

		def spy(company=None, herd=None):
			seen["company"] = company
			return "Dairy - KR", "herd"

		with patch.object(CC, "resolve_with_source", side_effect=spy):
			CC.stamp(Doc(rows, "Westwood Dairies"))
		self.assertEqual(seen["company"], "Westwood Dairies")




# ---------------------------------------------------------------------------
# The herd is the first place to look, and the company default is announced
# ---------------------------------------------------------------------------
#
# The chain above answered "some cost centre exists" but not "the right one".
# On live, nine of eleven herds already name `Dairy - KR` and nothing read it,
# so feed, milk, drugs and husbandry all posted to whatever the company default
# happened to be — `Main - KR`, which is the flower side. That is the quiet
# accounting error this module's own docstring warned about, arriving by a
# different door.
#
# So: the herd first, then a per-company row the dairy owns, and only then the
# company default — which still posts, because a farm hand mid-round must not
# be stopped by a finance setting, but says out loud that it is a fallback.


class TestTheHerdComesFirst(unittest.TestCase):
	def test_the_herds_own_cost_centre_wins(self):
		with patch.object(CC, "herd_cost_center", return_value="Dairy - KR"), patch.object(
			CC, "company_cost_center", side_effect=AssertionError("must not be asked")
		):
			self.assertEqual(CC.resolve("Karen Roses", herd="STEAMERS"), "Dairy - KR")

	def test_without_a_herd_the_per_company_row_answers(self):
		with patch.object(CC, "herd_cost_center", return_value=None), patch.object(
			CC, "setting_cost_center", return_value="Dairy - KR"
		):
			self.assertEqual(CC.resolve("Karen Roses"), "Dairy - KR")

	def test_a_herd_without_one_falls_through_to_the_setting(self):
		with patch.object(CC, "herd_cost_center", return_value=None), patch.object(
			CC, "setting_cost_center", return_value="Dairy - KR"
		):
			self.assertEqual(CC.resolve("Karen Roses", herd="Culled"), "Dairy - KR")

	def test_the_source_says_which_tier_answered(self):
		"""`stamp` needs to know, because only the company tier is announced."""
		with patch.object(CC, "herd_cost_center", return_value="Dairy - KR"):
			self.assertEqual(CC.resolve_with_source("Karen Roses", herd="STEAMERS"), ("Dairy - KR", "herd"))
		with patch.object(CC, "herd_cost_center", return_value=None), patch.object(
			CC, "setting_cost_center", return_value="Dairy - KR"
		):
			self.assertEqual(CC.resolve_with_source("Karen Roses"), ("Dairy - KR", "setting"))
		with patch.object(CC, "herd_cost_center", return_value=None), patch.object(
			CC, "setting_cost_center", return_value=None
		), patch.object(CC, "company_cost_center", return_value="Main - KR"):
			self.assertEqual(CC.resolve_with_source("Karen Roses"), ("Main - KR", "company"))
		with patch.object(CC, "herd_cost_center", return_value=None), patch.object(
			CC, "setting_cost_center", return_value=None
		), patch.object(CC, "company_cost_center", return_value=None):
			self.assertEqual(CC.resolve_with_source("Karen Roses"), (None, None))


class TestACostCentreHasToBeUsable(unittest.TestCase):
	"""Two refusals ERPNext would make anyway, made here so the chain can keep
	looking instead of dying on the first answer it finds."""

	def test_a_group_cost_centre_is_not_offered(self):
		group = frappe.db.get_value("Cost Center", {"is_group": 1, "company": "Karen Roses"}, "name")
		self.assertTrue(group, "kaitet.local needs a group cost centre for this test")
		self.assertFalse(CC.usable(group, "Karen Roses"))

	def test_a_cost_centre_from_another_company_is_not_offered(self):
		"""A herd naming a Westwood centre while the entry posts under Karen
		Roses is rejected by ERPNext outright, so the chain must look past it."""
		self.assertFalse(CC.usable("Dairy - KR", "Westwood Dairies"))

	def test_a_plain_leaf_of_the_right_company_is_fine(self):
		self.assertTrue(CC.usable("Dairy - KR", "Karen Roses"))

	def test_blank_is_never_usable(self):
		self.assertFalse(CC.usable(None, "Karen Roses"))
		self.assertFalse(CC.usable("", "Karen Roses"))

	def test_an_unusable_herd_centre_falls_through(self):
		"""Not an error: the herd is simply not the answer here."""
		with patch.object(CC, "_herd_field", return_value="Some Group - KR"), patch.object(
			CC, "usable", return_value=False
		):
			self.assertIsNone(CC.herd_cost_center("STEAMERS", "Karen Roses"))


class TestTheFallbackAnnouncesItself(unittest.TestCase):
	def test_using_the_company_default_tells_the_user(self):
		rows = [Row(cost_center="")]
		with patch.object(CC, "resolve_with_source", return_value=("Main - KR", "company")), patch.object(
			CC.frappe, "msgprint"
		) as said:
			CC.stamp(Doc(rows, "Karen Roses"), herd="STEAMERS")
		self.assertTrue(said.called, "the farm must be told it is on the fallback")
		msg = said.call_args.args[0] if said.call_args.args else said.call_args.kwargs["msg"]
		self.assertIn("Main - KR", msg)
		self.assertIn("STEAMERS", msg)

	def test_the_herds_own_centre_is_not_announced(self):
		"""Nothing to say: this is the cost centre the farm asked for."""
		rows = [Row(cost_center="")]
		with patch.object(CC, "resolve_with_source", return_value=("Dairy - KR", "herd")), patch.object(
			CC.frappe, "msgprint"
		) as said:
			CC.stamp(Doc(rows, "Karen Roses"), herd="STEAMERS")
		self.assertFalse(said.called)

	def test_the_per_company_setting_is_not_announced(self):
		rows = [Row(cost_center="")]
		with patch.object(CC, "resolve_with_source", return_value=("Dairy - KR", "setting")), patch.object(
			CC.frappe, "msgprint"
		) as said:
			CC.stamp(Doc(rows, "Karen Roses"))
		self.assertFalse(said.called)

	def test_the_message_never_takes_the_run_down(self):
		rows = [Row(cost_center="")]
		with patch.object(CC, "resolve_with_source", return_value=("Main - KR", "company")), patch.object(
			CC.frappe, "msgprint", side_effect=RuntimeError("no realtime here")
		):
			self.assertEqual(CC.stamp(Doc(rows, "Karen Roses")), 1)
		self.assertEqual(rows[0]["cost_center"], "Main - KR")


class TestThePerCompanySetting(unittest.TestCase):
	def test_the_child_table_exists_on_livestock_settings(self):
		"""Replaces the flat custom_default_cost_center: one dairy, several
		companies, and the flower side must not inherit the dairy's centre."""
		self.assertTrue(frappe.get_meta(CC.SETTINGS).has_field(CC.SETTINGS_TABLE))

	def test_it_is_a_table_of_company_and_cost_centre(self):
		f = frappe.get_meta(CC.SETTINGS).get_field(CC.SETTINGS_TABLE)
		self.assertEqual(f.fieldtype, "Table")
		meta = frappe.get_meta(f.options)
		self.assertEqual(meta.get_field("company").options, "Company")
		self.assertEqual(meta.get_field("cost_center").options, "Cost Center")

	def test_only_the_row_for_that_company_is_used(self):
		rows = [
			frappe._dict(company="Karen Roses", cost_center="Dairy - KR"),
			frappe._dict(company="Westwood Dairies", cost_center="Main - WDL"),
		]
		with patch.object(CC, "_setting_rows", return_value=rows), patch.object(
			CC, "usable", return_value=True
		):
			self.assertEqual(CC.setting_cost_center("Westwood Dairies"), "Main - WDL")

	def test_a_company_with_no_row_gets_nothing(self):
		with patch.object(CC, "_setting_rows", return_value=[]):
			self.assertIsNone(CC.setting_cost_center("Karen Roses"))


class TestTheHerdFieldCanActuallyBeSet(unittest.TestCase):
	"""Herds is submittable and nine of eleven live herds are submitted, so
	every field without `allow_on_submit` is frozen on the form. The cost
	centre was one of them: the farm could see it and could not change it."""

	def test_the_cost_centre_is_editable_after_submit(self):
		f = frappe.get_meta("Herds").get_field("cost_center")
		self.assertTrue(f.allow_on_submit, "a submitted herd's cost centre must stay settable")

	def test_it_is_a_link_to_cost_center(self):
		f = frappe.get_meta("Herds").get_field("cost_center")
		self.assertEqual(f.fieldtype, "Link")
		self.assertEqual(f.options, "Cost Center")

	def test_there_is_only_one_cost_centre_field_left(self):
		"""Herds carried `cost_center` AND `custom_cost_center`, both labelled
		"Cost Center". On the live site they held different values on the same
		herd, so "the herd's cost centre" had two answers."""
		fields = [f.fieldname for f in frappe.get_meta("Herds").fields if "cost_center" in f.fieldname]
		self.assertEqual(fields, ["cost_center"])
