# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from upande_livestock.patches.backfill_standing_ration_boms import _first_fed_herd, execute
from upande_livestock.serverscripts.feeding._engine import get_herd_feeding_program
from upande_livestock.serverscripts.feeding.manual_feed import manual_feed
from upande_livestock.serverscripts.tests.test_operations import _open_backdating_window

FIELDS = ["custom_herd", "custom_is_livestock_feed", "custom_ration_kind"]
# custom_is_livestock_feed (Check) is a NOT NULL column; None only works for
# the Link and Select fields.
BLANK = {"custom_herd": None, "custom_is_livestock_feed": 0, "custom_ration_kind": ""}


def _shared_boms():
	"""bom_name -> [herds] for every standing BOM shared by 2+ herds."""
	counts = {}
	for row in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"]):
		counts.setdefault(row.bom, []).append(row.name)
	return {bom: herds for bom, herds in counts.items() if len(herds) > 1}


def _ever_fed(herd, item):
	"""Whether `herd` has a submitted Feeding event whose Stock Entry issued
	`item` — the same fact _first_fed_herd resolves on, checked directly."""
	return bool(_first_fed_herd(item, [herd]))


def _a_feedable_herd(herds):
	"""Of `herds`, one that can actually be run through manual_feed on this
	site (a BOM, animals, and a feeding program that allows manufacture)."""
	for herd in herds:
		row = frappe.db.get_value("Herds", herd, ["bom", "number_of_animals"], as_dict=True)
		if row and row.bom and (row.number_of_animals or 0) > 0:
			if get_herd_feeding_program(herd)["can_manufacture"]:
				return herd
	return None


class TestBackfillStandingRationBoms(IntegrationTestCase):
	def setUp(self):
		# Every case here feeds a herd on a past date to give the backfill
		# something to attribute. That is a backdated write, refused outright
		# while the window is shut — so this class passed only on a site where
		# some other module had left the window open, and failed on a clean one.
		_open_backdating_window(self)

	def _reset(self, bom_name):
		"""Blank the three fields on `bom_name` and remember their original
		values so tearDown can put them back — this patch commits, so a plain
		rollback will not undo it."""
		original = frappe.db.get_value("BOM", bom_name, FIELDS, as_dict=True)
		self.addCleanup(self._restore, bom_name, original)
		for fieldname, blank in BLANK.items():
			frappe.db.set_value("BOM", bom_name, fieldname, blank, update_modified=False)
		frappe.db.commit()

	def _restore(self, bom_name, original):
		for fieldname in FIELDS:
			value = original.get(fieldname)
			if value is None and fieldname in BLANK:
				value = BLANK[fieldname]
			frappe.db.set_value("BOM", bom_name, fieldname, value, update_modified=False)
		frappe.db.commit()

	def _a_solo_herd(self):
		"""A herd whose BOM only that one herd points at."""
		counts = {}
		for row in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"]):
			counts.setdefault(row.bom, []).append(row.name)
		for bom_name, herds in counts.items():
			if len(herds) == 1:
				return herds[0], bom_name
		raise AssertionError("kaitet.local has no herd whose standing BOM is unshared")

	def _a_shared_bom(self):
		shared = _shared_boms()
		if not shared:
			raise AssertionError("kaitet.local has no BOM shared by two herds")
		bom_name = next(iter(shared))
		return bom_name, shared[bom_name]

	def test_a_solo_herds_bom_is_stamped_standing_with_the_herd(self):
		herd, bom_name = self._a_solo_herd()
		self._reset(bom_name)

		execute()

		got = frappe.db.get_value("BOM", bom_name, FIELDS, as_dict=True)
		self.assertEqual(got.custom_herd, herd)
		self.assertEqual(got.custom_is_livestock_feed, 1)
		self.assertEqual(got.custom_ration_kind, "Standing")

	def test_a_shared_bom_is_stamped_standing_regardless_of_attribution(self):
		"""Whatever custom_herd ends up as (a herd, or blank — see the rule
		tested below), the BOM is livestock feed / Standing either way."""
		bom_name, herds = self._a_shared_bom()
		self.assertEqual(len(herds), 2)
		self._reset(bom_name)

		execute()

		got = frappe.db.get_value("BOM", bom_name, FIELDS, as_dict=True)
		self.assertIn(got.custom_herd, [None, "", *herds])
		self.assertEqual(got.custom_is_livestock_feed, 1)
		self.assertEqual(got.custom_ration_kind, "Standing")

	def test_a_shared_bom_with_only_one_herd_ever_fed_resolves_to_that_herd(self):
		"""The real case on kaitet.local: BOM-Dry/Steamers/Incalf Heifers-012
		is the standing ration for both INCALF HEIFERS and STEAMERS, but only
		INCALF HEIFERS has ever actually been fed it."""
		bom_name = "BOM-Dry/Steamers/Incalf Heifers-012"
		herds = ["INCALF HEIFERS", "STEAMERS"]
		if frappe.db.get_value("Herds", herds[0], "bom") != bom_name or frappe.db.get_value(
			"Herds", herds[1], "bom"
		) != bom_name:
			self.skipTest(f"{herds} no longer share {bom_name} on this site")
		item = frappe.db.get_value("BOM", bom_name, "item")
		fed = [h for h in herds if _ever_fed(h, item)]
		if fed != ["INCALF HEIFERS"]:
			self.skipTest(
				f"expected only INCALF HEIFERS to have feeding history for {item}, got {fed}"
			)
		self._reset(bom_name)

		execute()

		self.assertEqual(frappe.db.get_value("BOM", bom_name, "custom_herd"), "INCALF HEIFERS")

	def test_a_shared_bom_with_neither_herd_ever_fed_stays_blank(self):
		"""'Fed first' has no answer when nobody has been fed it; a blank
		stays more honest than a guess."""
		self.assertIsNone(_first_fed_herd("NO-SUCH-ITEM-WAS-EVER-FED", ["0-2", "2-4"]))

	def test_a_same_date_tie_breaks_by_earlier_creation(self):
		"""Two herds sharing a BOM, both first fed it on the same calendar
		date: whichever event was actually entered first (by `creation`)
		wins — that is the tiebreak the module docstring names.

		Built with the real feeding engine (manual_feed), not raw SQL rows,
		so the fixture is the same shape production data actually takes.
		manual_feed/_engine never call frappe.db.commit() themselves (see
		_engine.py), so this stays inside the test's own transaction and
		tearDown's rollback undoes all of it — no real stock movement is
		left behind.
		"""
		bom_name, herds = None, None
		for candidate_bom, candidate_herds in _shared_boms().items():
			if len(candidate_herds) == 2 and _a_feedable_herd(candidate_herds) and _a_feedable_herd(
				list(reversed(candidate_herds))
			):
				bom_name, herds = candidate_bom, candidate_herds
				break
		if not bom_name or not all(_a_feedable_herd([h]) for h in herds):
			self.skipTest("no shared-BOM herd pair on this site can both be fed via manual_feed")

		employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not employee:
			self.skipTest("no active Employee on this site")

		item = frappe.db.get_value("BOM", bom_name, "item")
		bom = frappe.get_doc("BOM", bom_name)
		lines = [{"item_code": r.item_code, "qty": flt(r.qty) * 0.02} for r in bom.items]
		posting_date = add_days(today(), -2)

		first, second = herds[0], herds[1]
		res1 = manual_feed(
			{"herd": first, "lines": lines, "heads": 2, "posting_date": posting_date, "employee": employee}
		)
		self.assertNotIn("error", res1, res1.get("error"))
		res2 = manual_feed(
			{"herd": second, "lines": lines, "heads": 2, "posting_date": posting_date, "employee": employee}
		)
		self.assertNotIn("error", res2, res2.get("error"))

		# Both events landed on the same event_date; `first` was entered
		# (created) strictly before `second`.
		self.assertEqual(
			frappe.db.get_value("Livestock Event", res1["livestock_event"], "event_date"),
			frappe.db.get_value("Livestock Event", res2["livestock_event"], "event_date"),
		)

		self.assertEqual(_first_fed_herd(item, [first, second]), first)
		self.assertEqual(_first_fed_herd(item, [second, first]), first)

		frappe.db.rollback()

	def test_the_herds_own_bom_link_is_untouched(self):
		"""The backfill only stamps the BOM side; it must not repoint
		Herds.bom or Item.default_bom."""
		herd, bom_name = self._a_solo_herd()
		before_herd_bom = frappe.db.get_value("Herds", herd, "bom")
		before_item = frappe.db.get_value("BOM", bom_name, "item")
		before_default_bom = frappe.db.get_value("Item", before_item, "default_bom")
		self._reset(bom_name)

		execute()

		self.assertEqual(frappe.db.get_value("Herds", herd, "bom"), before_herd_bom)
		self.assertEqual(frappe.db.get_value("Item", before_item, "default_bom"), before_default_bom)

	def test_the_backfill_is_idempotent(self):
		herd, bom_name = self._a_solo_herd()
		self._reset(bom_name)

		execute()
		execute()

		got = frappe.db.get_value("BOM", bom_name, FIELDS, as_dict=True)
		self.assertEqual(got.custom_herd, herd)
		self.assertEqual(got.custom_is_livestock_feed, 1)
		self.assertEqual(got.custom_ration_kind, "Standing")

	def test_rerunning_after_a_correct_shared_attribution_does_not_churn_it(self):
		"""The patch has already run once on this site. Re-running it with
		the same feeding history must reproduce the same attribution, not
		flip it or blank it out."""
		bom_name, herds = self._a_shared_bom()
		self._reset(bom_name)

		execute()
		first_pass = frappe.db.get_value("BOM", bom_name, "custom_herd")
		execute()
		second_pass = frappe.db.get_value("BOM", bom_name, "custom_herd")

		self.assertEqual(first_pass, second_pass)
