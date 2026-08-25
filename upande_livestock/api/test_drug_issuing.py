# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Drugs must actually leave the store when an animal is treated.

The farm ran 93 vaccinations, 50 services and 25 health cases without moving one
gram of stock. Five things caused that, and each has a test here:

  * drug rows were optional and an empty table passed silently;
  * the picker summed stock farm-wide, so it offered drugs the drug store did
    not hold and the issue then failed;
  * a failed issue was downgraded to a toast nobody saw — it now blocks;
  * treatments could not be recorded at all except on the desk form, and the
    case's single stock-entry guard would have swallowed every round after the
    first anyway;
  * dosing had no notion of a herd, so a whole-herd round had to be entered one
    cow at a time or not at all.

Read-only where it can be. The tests that post stock skip when the drug store
has nothing to draw on, because an unseeded site is a missing fixture rather
than a broken feature:

    bench --site <site> execute upande_livestock.demo.seed_test_stock.run
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from upande_livestock import livestock_stock
from upande_livestock.api import operations
from upande_livestock.api.test_operations import _make_cow, _purge, _purge_events_for


def _drug_store():
	return livestock_stock.drug_warehouse()


def _stocked_drug(min_qty=1):
	"""The drug with the most stock in the drug store, or None.

	Deepest first, so a test that needs one unit per cow can actually find a herd
	it can dose rather than skipping.
	"""
	warehouse = _drug_store()
	if not warehouse:
		return None
	rows = frappe.get_all(
		"Bin",
		filters=[["warehouse", "=", warehouse], ["actual_qty", ">=", min_qty]],
		fields=["item_code", "actual_qty"],
		order_by="actual_qty desc",
		limit=50,
	)
	for r in rows:
		if frappe.db.get_value("Item", r.item_code, "item_group") == "DRUGS":
			return r
	return None


class TestAvailabilityCheck(IntegrationTestCase):
	"""check_availability is what turns a raw ERPNext negative-stock error into a
	message naming the drug and the gap."""

	def test_rows_for_the_same_item_compete_for_one_balance(self):
		"""Two lines of the same drug out of the same store must be summed. Checked
		independently, a pair that together overdraws the shelf would both pass."""
		drug = _stocked_drug()
		if not drug:
			raise unittest.SkipTest("no drug stock on this site")
		have = flt(drug.actual_qty)
		half = have / 2 + 1
		rows = [
			{"item_code": drug.item_code, "qty": half, "warehouse": _drug_store()},
			{"item_code": drug.item_code, "qty": half, "warehouse": _drug_store()},
		]
		short = livestock_stock.check_availability(rows)
		self.assertTrue(short, "two half-plus-one lines must overdraw the balance")
		self.assertAlmostEqual(short[0]["required"], half * 2, places=4)

	def test_a_covered_row_reports_nothing(self):
		drug = _stocked_drug()
		if not drug:
			raise unittest.SkipTest("no drug stock on this site")
		rows = [{"item_code": drug.item_code, "qty": 1, "warehouse": _drug_store()}]
		self.assertEqual(livestock_stock.check_availability(rows), [])

	def test_blank_and_zero_rows_are_ignored(self):
		self.assertEqual(livestock_stock.check_availability([]), [])
		self.assertEqual(
			livestock_stock.check_availability(
				[{"item_code": None, "qty": 5, "warehouse": "X"}, {"item_code": "A", "qty": 0, "warehouse": "X"}]
			),
			[],
		)

	def test_issue_blocks_rather_than_warning(self):
		"""The reversal that this whole change turns on."""
		drug = _stocked_drug()
		if not drug:
			raise unittest.SkipTest("no drug stock on this site")
		rows = [
			{"item_code": drug.item_code, "qty": flt(drug.actual_qty) + 1000, "warehouse": _drug_store()}
		]
		with self.assertRaises(frappe.ValidationError):
			livestock_stock.issue_items(rows, remarks="test", employee="_none_")


class TestStoreScopedPicker(IntegrationTestCase):
	def test_the_picker_reports_the_chosen_store_not_the_farm(self):
		"""Summing every warehouse offered drugs the drug store did not have."""
		warehouse = _drug_store()
		if not warehouse:
			raise unittest.SkipTest("no drug store configured")
		scoped = operations._stock_items("drug", warehouse)
		if not scoped:
			raise unittest.SkipTest("no drug stock on this site")
		for row in scoped:
			self.assertAlmostEqual(
				row["qty"],
				flt(frappe.db.get_value("Bin", {"item_code": row["value"], "warehouse": warehouse}, "actual_qty")),
				places=4,
			)

	def test_an_empty_store_offers_nothing(self):
		self.assertEqual(operations._stock_items("drug", "__no_such_warehouse__"), [])


class TestHerdTargeting(IntegrationTestCase):
	"""Dosing is per animal; the head count comes from live animals."""

	def _herd(self):
		rows = frappe.get_all("Herds", fields=["name", "number_of_animals"], limit=50)
		for h in rows:
			if operations._animals_in_herd(h.name):
				return h
		return None

	def test_a_herd_resolves_to_its_live_animals(self):
		herd = self._herd()
		if not herd:
			raise unittest.SkipTest("no herd on this site has live animals")
		targets = operations._husbandry_targets({"herd": herd.name})
		self.assertEqual(sorted(targets), sorted(a.name for a in operations._animals_in_herd(herd.name)))

	def test_retired_animals_are_never_dosed(self):
		"""Herds.number_of_animals counts every animal pointing at the herd,
		retired ones included — dosing off it would issue drugs for dead cows."""
		herd = self._herd()
		if not herd:
			raise unittest.SkipTest("no herd on this site has live animals")
		for name in operations._husbandry_targets({"herd": herd.name}):
			status, disabled = frappe.db.get_value("Animal", name, ["status", "disabled"])
			self.assertNotIn(status, operations._RETIRED_STATUSES)
			self.assertFalse(disabled)

	def test_an_explicit_list_wins_over_a_herd(self):
		herd = self._herd()
		if not herd:
			raise unittest.SkipTest("no herd on this site has live animals")
		some = [a.name for a in operations._animals_in_herd(herd.name)][:2]
		self.assertEqual(operations._husbandry_targets({"herd": herd.name, "animals": some}), some)

	def test_no_target_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			operations._husbandry_targets({})

	def test_an_empty_herd_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			operations._husbandry_targets({"herd": "__no_such_herd__"})


class TestPerAnimalDosing(IntegrationTestCase):
	"""The round is dosed per animal and issued once.

	Its own herd and its own cows, rather than a real one: the deworming interval
	guard refuses an animal treated in the last 90 days, so a test that reused a
	live herd would pass or skip depending on what the farm did that week.
	"""

	HERD = "ZZ DRUG TEST HERD"
	TAGS = ("ZZ DRUG COW 1", "ZZ DRUG COW 2", "ZZ DRUG COW 3")

	def setUp(self):
		self.drug = _stocked_drug(min_qty=len(self.TAGS))
		if not self.drug:
			raise unittest.SkipTest("no drug with enough stock on this site")
		if not frappe.db.exists("Herds", self.HERD):
			frappe.get_doc({"doctype": "Herds", "herd_name": self.HERD}).insert(ignore_permissions=True)
		self.cows = [_make_cow(tag, herd=self.HERD) for tag in self.TAGS]
		for cow in self.cows:
			self.addCleanup(_purge_events_for, cow.name)
			self.addCleanup(_purge, "Animal", cow.name)
		self.addCleanup(_purge, "Herds", self.HERD)

	def test_quantities_are_per_animal(self):
		"""2 ml a cow across N cows leaves the store as one line of 2N."""
		heads = len(self.cows)
		self.assertEqual(len(operations._animals_in_herd(self.HERD)), heads)

		def bal():
			return flt(
				frappe.db.get_value(
					"Bin", {"item_code": self.drug.item_code, "warehouse": _drug_store()}, "actual_qty"
				)
			)

		before = bal()
		res = operations.create_husbandry_event(
			{
				"event_type": "Deworming",
				"herd": self.HERD,
				"event_date": today(),
				"operator": frappe.db.get_value("Employee", {"status": "Active"}, "name"),
				"drugs": [{"item_code": self.drug.item_code, "qty": 1}],
			}
		)
		self.assertFalse(res.get("error"), res.get("error"))
		for name in res["names"]:
			self.addCleanup(_purge, "Livestock Event", name)

		self.assertEqual(res["animals"], heads)
		self.assertAlmostEqual(before - bal(), heads, places=4)

		# One issue for the round, and every event points at it — so no event
		# posts a second time through post_stock_issue's own path.
		events = frappe.get_all(
			"Livestock Event", filters={"name": ["in", res["names"]]}, fields=["name", "stock_entry"]
		)
		self.assertEqual(len(events), heads)
		self.assertTrue(all(e.stock_entry == res["stock_entry"] for e in events))
		se = frappe.get_doc("Stock Entry", res["stock_entry"])
		self.assertEqual(len(se.items), 1)
		self.assertAlmostEqual(se.items[0].qty, heads, places=4)

		# The clinical record stays per animal — withdrawal is a per-cow fact.
		rows = frappe.get_all("Livestock Drug Issue", filters={"parent": ["in", res["names"]]}, fields=["qty"])
		self.assertEqual(len(rows), heads)
		self.assertTrue(all(flt(r.qty) == 1 for r in rows))

	def test_a_round_the_store_cannot_cover_creates_nothing(self):
		"""Blocking has to mean nothing was written, not a half-done round."""
		before = frappe.db.count("Livestock Event", {"event_type": "Deworming"})
		res = operations.create_husbandry_event(
			{
				"event_type": "Deworming",
				"herd": self.HERD,
				"event_date": today(),
				"operator": frappe.db.get_value("Employee", {"status": "Active"}, "name"),
				"drugs": [{"item_code": self.drug.item_code, "qty": flt(self.drug.actual_qty) + 100}],
			}
		)
		self.assertTrue(res.get("error"))
		self.assertIn("cannot cover", res["error"])
		self.assertEqual(frappe.db.count("Livestock Event", {"event_type": "Deworming"}), before)


class TestConsumesDrugsFlag(IntegrationTestCase):
	def test_the_flag_drives_which_types_issue(self):
		"""Read off Livestock Event Type, not a tuple in code, so the farm can flag
		dry-cow therapy or calcium at calving without a deploy."""
		for name in ("Vaccination", "Deworming"):
			if frappe.db.exists("Livestock Event Type", name):
				self.assertTrue(operations._type_consumes_drugs(name))
		for name in ("Movement", "Weight Recording"):
			if frappe.db.exists("Livestock Event Type", name):
				self.assertFalse(operations._type_consumes_drugs(name))

	def test_an_unknown_type_falls_back_to_the_old_tuple(self):
		self.assertFalse(operations._type_consumes_drugs("__no_such_type__"))
