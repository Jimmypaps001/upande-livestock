# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""An animal arriving bought rather than born.

The mirror of culling, and it turns on the same thing culling does: the farm's
own register decides who she is. THE SELLER'S TAG IS NOT HER NAME. Every screen
in this app, and the book on the wall, calls an animal by the farm's number —
A057/26 for a heifer, B014/26 for a bull — and an animal that arrived carrying
somebody else's numbering would be the one record nobody could find twice.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import animal_id
from upande_livestock.serverscripts.common.animal import recompute_herd_count
from upande_livestock.serverscripts.herds.buy_in_animal import buy_in_animal
from upande_livestock.serverscripts.tests.test_culling import _employee

HERD = "INCALF HEIFERS"


def _forget(tag):
	"""Undo a buy-in completely, in the order that permits it."""
	frappe.set_user("Administrator")
	if not frappe.db.exists("Animal", tag):
		frappe.db.commit()
		return
	doc = frappe.get_doc("Animal", tag)
	for name in frappe.get_all("Livestock Event", filters={"animal": tag}, pluck="name"):
		event = frappe.get_doc("Livestock Event", name)
		if event.docstatus == 1:
			event.cancel()
		frappe.delete_doc("Livestock Event", name, force=True, ignore_permissions=True)
	if doc.asset_link and frappe.db.exists("Asset", doc.asset_link):
		asset = frappe.get_doc("Asset", doc.asset_link)
		if asset.docstatus == 1:
			asset.cancel()
		frappe.delete_doc("Asset", doc.asset_link, force=True, ignore_permissions=True)
	herd = doc.current_herd
	frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
	if herd:
		recompute_herd_count(herd)
	frappe.db.commit()


class TestBuyingAnAnimalIn(IntegrationTestCase):
	def setUp(self):
		self.bought = []
		self.addCleanup(lambda: [_forget(t) for t in self.bought])

	def _buy(self, **over):
		payload = {"sex": "Female", "herd": HERD, "name_given": "ZZ BOUGHT",
		           "operator": _employee(), **over}
		got = buy_in_animal(payload)
		if got.get("ok"):
			self.bought.append(got["animal"])
		return got

	def test_she_gets_the_farms_next_number_not_the_sellers(self):
		got = self._buy(seller_tag="KD-441")
		self.assertTrue(got.get("ok"), got.get("error"))
		parsed = animal_id.parse(got["animal"])
		self.assertIsNotNone(parsed, f"{got['animal']} is not a farm register number")
		self.assertEqual(parsed["prefix"], "A")

	def test_a_bull_is_numbered_in_the_bull_series(self):
		got = self._buy(sex="Male", herd="BULLS")
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(animal_id.parse(got["animal"])["prefix"], "B")

	def test_the_sellers_tag_is_kept_but_not_used_as_her_name(self):
		"""A dispute about which animal was sold is settled by their number."""
		got = self._buy(seller_tag="KD-441")
		self.assertNotEqual(got["animal"], "KD-441")
		self.assertEqual(frappe.db.get_value("Animal", got["animal"], "book_number"), "KD-441")

	def test_she_arrives_into_a_herd_and_the_count_follows(self):
		before = frappe.db.get_value("Herds", HERD, "number_of_animals")
		got = self._buy()
		self.assertEqual(got["herd"], HERD)
		self.assertEqual(
			frappe.db.get_value("Herds", HERD, "number_of_animals"), before + 1)

	def test_her_timeline_opens_with_the_day_she_came(self):
		"""Not with a record that was simply always there."""
		got = self._buy(seller="Kabiyet Dairies")
		event = frappe.db.get_value(
			"Livestock Event", {"animal": got["animal"], "event_type": "Movement"},
			["new_herd", "remarks"], as_dict=True)
		self.assertEqual(event.new_herd, HERD)
		self.assertIn("Kabiyet Dairies", event.remarks)

	def test_what_she_cost_puts_her_on_the_books(self):
		got = self._buy(purchase_value=120000)
		self.assertTrue(got["asset"], "a bought animal was not capitalised")
		row = frappe.db.get_value(
			"Animal", got["animal"],
			["is_capitalised", "purchase_value", "current_book_value"], as_dict=True)
		self.assertEqual(row.is_capitalised, 1)
		self.assertEqual(row.purchase_value, 120000)
		self.assertEqual(row.current_book_value, 120000)

	def test_an_animal_that_cost_nothing_is_not_capitalised(self):
		"""A gift, or a transfer in. An Asset worth nothing makes the balance
		sheet longer and says less."""
		got = self._buy()
		self.assertIsNone(got["asset"])
		self.assertFalse(frappe.db.get_value("Animal", got["animal"], "is_capitalised"))

	def test_how_she_arrived_is_recorded_and_a_gift_is_not_a_purchase(self):
		"""`origin` answers "where did this farm's animals come from", and the
		field's own vocabulary already separates the two."""
		bought = self._buy(purchase_value=90000)
		given = self._buy()
		self.assertEqual(frappe.db.get_value("Animal", bought["animal"], "origin"), "Purchased")
		self.assertEqual(
			frappe.db.get_value("Animal", given["animal"], "origin"), "Transferred In")

	def test_she_cannot_arrive_before_she_was_born(self):
		got = self._buy(date_of_birth=add_days(today(), -1), arrival_date=add_days(today(), -30))
		self.assertIn("before she was born", got.get("error", ""))

	def test_she_cannot_arrive_tomorrow(self):
		got = self._buy(arrival_date=add_days(today(), 1))
		self.assertTrue(got.get("error"))

	def test_a_sex_nobody_stated_is_refused(self):
		"""It decides her number series, so it cannot be guessed."""
		got = self._buy(sex="")
		self.assertIn("female", got.get("error", "").lower())

	def test_a_herd_that_is_not_there_is_refused(self):
		got = self._buy(herd="NO SUCH HERD")
		self.assertIn("not a herd", got.get("error", ""))

	def test_two_bought_in_the_same_day_get_different_numbers(self):
		first = self._buy()
		second = self._buy()
		self.assertTrue(second.get("ok"), second.get("error"))
		self.assertNotEqual(first["animal"], second["animal"])

	def test_a_number_already_in_use_is_refused_with_the_free_ones(self):
		"""A farm worker correcting a number needs the free ones, not an error."""
		taken = frappe.db.get_value("Animal", {"sex": "Female", "disabled": 0}, "name")
		if not animal_id.parse(taken or ""):
			self.skipTest("no register-numbered female on this site")
		got = self._buy(tag_number=taken)
		self.assertIn("already belongs to", got.get("error", ""))
