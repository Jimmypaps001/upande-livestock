"""BOM's back-link to the herd its ration was made for.

`BOM` is a core ERPNext doctype, so the fields are Custom Fields (see
fixtures/custom_field.json), not a DocType JSON edit — same route
upande_scp took for its own BOM fields. custom_livestock_tab only shows when
custom_is_livestock_feed is set, since depends_on can only evaluate this
document's own fields, not the item's group.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding._tuned_bom import tuned_bom


def _a_herd():
	name = frappe.db.get_value("Herds", {"bom": ["is", "set"]}, "name")
	if not name:
		raise AssertionError("kaitet.local has no herd with a BOM")
	return name


class TestBomHerdLinkFields(IntegrationTestCase):
	"""The four Custom Fields exist on BOM with the shape the model needs."""

	def test_the_tab_is_a_tab_break_gated_on_the_check(self):
		field = frappe.get_meta("BOM").get_field("custom_livestock_tab")
		self.assertIsNotNone(field, "BOM has no custom_livestock_tab")
		self.assertEqual(field.fieldtype, "Tab Break")
		self.assertEqual(field.depends_on, "eval:doc.custom_is_livestock_feed")

	def test_the_herd_field_links_to_herds(self):
		field = frappe.get_meta("BOM").get_field("custom_herd")
		self.assertIsNotNone(field, "BOM has no custom_herd")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Herds")

	def test_the_is_livestock_feed_field_is_a_check(self):
		field = frappe.get_meta("BOM").get_field("custom_is_livestock_feed")
		self.assertIsNotNone(field, "BOM has no custom_is_livestock_feed")
		self.assertEqual(field.fieldtype, "Check")

	def test_the_ration_kind_field_says_which_of_the_three_a_bom_is(self):
		"""Concentrate joins Standing and Tuned: a concentrate is mixed for the
		store rather than for a herd, and the pages that read this field must
		not mistake one for a herd's own ration."""
		field = frappe.get_meta("BOM").get_field("custom_ration_kind")
		self.assertIsNotNone(field, "BOM has no custom_ration_kind")
		self.assertEqual(field.fieldtype, "Select")
		self.assertEqual(field.options, "\nStanding\nTuned\nConcentrate")

	def test_the_tab_is_hidden_on_a_non_livestock_bom(self):
		"""depends_on keys on custom_is_livestock_feed, not the item's group —
		it can only evaluate the document's own fields. A BOM with the flag
		unset (any non-livestock BOM, e.g. upande_scp's tank-mix BOMs) must
		hide the tab."""
		custom_field = frappe.get_doc("Custom Field", "BOM-custom_livestock_tab")
		self.assertEqual(custom_field.depends_on, "eval:doc.custom_is_livestock_feed")


class TestTunedBomCarriesTheHerdLink(IntegrationTestCase):
	def setUp(self):
		self.herd = _a_herd()
		self.base = frappe.get_doc("BOM", frappe.db.get_value("Herds", self.herd, "bom"))
		self.lines = [
			{"item_code": row.item_code, "qty": flt(row.qty)} for row in self.base.items
		]

	def tearDown(self):
		frappe.db.rollback()

	def _tuned(self):
		lines = [dict(row) for row in self.lines]
		lines[0]["qty"] = flt(lines[0]["qty"]) + 5
		return lines

	def test_a_tuned_bom_carries_the_herd_the_check_and_tuned(self):
		doc = frappe.get_doc("BOM", tuned_bom(self.herd, self._tuned()))
		self.assertEqual(doc.custom_herd, self.herd)
		self.assertEqual(doc.custom_is_livestock_feed, 1)
		self.assertEqual(doc.custom_ration_kind, "Tuned")

	def test_the_herds_own_bom_is_untouched_by_tuning(self):
		"""Herds.bom and Item.default_bom must still point where they did —
		the herd's BOM is the standing ration, never reassigned."""
		tuned_bom(self.herd, self._tuned())
		self.assertEqual(frappe.db.get_value("Herds", self.herd, "bom"), self.base.name)
		self.assertEqual(
			frappe.db.get_value("Item", self.base.item, "default_bom"), self.base.name
		)


class TestBackfilledStandingRations(IntegrationTestCase):
	"""The patch (patches/backfill_standing_ration_boms.py) has already run on
	this site by the time tests execute. This checks the real result, the same
	way test_tuned_bom.py's _a_herd() trusts kaitet.local's real herd data."""

	def test_a_solo_standing_bom_carries_its_herd(self):
		herd = "12 MONTHS-SERVICE (BULLYING HEIFERS)"
		bom_name = frappe.db.get_value("Herds", herd, "bom")
		if not bom_name:
			self.skipTest(f"{herd} has no BOM on this site")
		got = frappe.db.get_value(
			"BOM", bom_name, ["custom_herd", "custom_is_livestock_feed", "custom_ration_kind"], as_dict=True
		)
		self.assertEqual(got.custom_herd, herd)
		self.assertEqual(got.custom_is_livestock_feed, 1)
		self.assertEqual(got.custom_ration_kind, "Standing")

	def test_a_shared_standing_bom_is_attributed_to_whichever_herd_was_fed_first(self):
		"""BOM-TMR Calves Meal-011 is the standing ration for both 0-2 and
		2-4. A single custom_herd cannot hold both, so the backfill resolves
		it to whichever herd's Feeding history says was actually fed this
		ration first — see the patch module's docstring for the rule and its
		tiebreak. On kaitet.local that is 0-2."""
		bom_name = frappe.db.get_value("Herds", "0-2", "bom")
		if not bom_name or frappe.db.get_value("Herds", "2-4", "bom") != bom_name:
			self.skipTest("0-2 and 2-4 no longer share a BOM on this site")
		got = frappe.db.get_value(
			"BOM", bom_name, ["custom_herd", "custom_is_livestock_feed", "custom_ration_kind"], as_dict=True
		)
		self.assertEqual(got.custom_herd, "0-2")
		self.assertEqual(got.custom_is_livestock_feed, 1)
		self.assertEqual(got.custom_ration_kind, "Standing")
