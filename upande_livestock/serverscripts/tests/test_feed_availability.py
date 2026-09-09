import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.feeding import _availability


def _a_herd_bom():
	name = frappe.db.get_value("Herds", {"bom": ["is", "set"]}, "bom")
	if not name:
		raise AssertionError("kaitet.local has no herd with a BOM")
	return name


class TestFeedAvailability(IntegrationTestCase):
	def setUp(self):
		self.bom = _a_herd_bom()

	def test_a_long_past_date_is_short(self):
		"""The farm's stock history does not reach back a year, so every line
		must report short rather than silently pass."""
		short = _availability.shortfalls_on(self.bom, 100, add_days(today(), -365))
		self.assertTrue(short, "expected shortfalls a year before any stock existed")
		for row in short:
			self.assertIn("item_code", row)
			self.assertGreater(row["short"], 0)

	def test_today_matches_the_engine(self):
		"""Today's answer must agree with resolve_requirement, which reads Bin.
		Two different answers for the same day is the bug this guards."""
		from upande_livestock.serverscripts.feeding._engine import resolve_requirement

		_, lines = resolve_requirement(self.bom, 100)
		engine_short = {ln["item_code"] for ln in lines if ln["short_qty"] > 0}
		ours = {r["item_code"] for r in _availability.shortfalls_on(self.bom, 100, today())}
		self.assertEqual(ours, engine_short)

	def test_assert_names_every_short_item_and_a_date(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			_availability.assert_can_cover_on(self.bom, 100, add_days(today(), -365))
		message = str(caught.exception)
		self.assertIn("store held", message)
		self.assertIn("Nothing was posted", message)

	def test_assert_passes_when_the_stores_can_cover_it(self):
		"""A trivially small run against today must not throw."""
		_availability.assert_can_cover_on(self.bom, 0.001, today())

	def test_earliest_workable_date_is_none_when_never_workable(self):
		self.assertIsNone(
			_availability.earliest_workable_date(
				self.bom, 10 ** 9, add_days(today(), -30), today()
			)
		)

	def test_earliest_workable_date_finds_today_for_a_tiny_run(self):
		found = _availability.earliest_workable_date(
			self.bom, 0.001, add_days(today(), -30), today()
		)
		self.assertIsNotNone(found)
