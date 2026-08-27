# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The farm's own register number, and the herd an animal is actually in.

A book number — A028/19 — is a letter, a sequence and the year of birth. It is
what people say out loud about an animal, and until now the system held none of
them. It is a FIELD rather than the document's name: four of the 298 entries are
not register numbers at all, 24 animals in the inventory do not exist here yet,
and a naming scheme that cannot name every record is not a naming scheme.
"""

import re
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.demo.place_herd_inventory import HERD, _clean_book


class TestBookNumberTidying(IntegrationTestCase):
	"""Two transcription habits run through the sheet. Neither invents a number."""

	def test_a_letter_o_becomes_the_zero_it_was_meant_to_be(self):
		"""AO63/20 sits beside A028/19 — one series typed two ways."""
		self.assertEqual(_clean_book("AO63/20"), "A063/20")
		self.assertEqual(_clean_book("Ao63/20"), "A063/20")

	def test_a_backslash_becomes_the_separator(self):
		self.assertEqual(_clean_book("A053\\25"), "A053/25")

	def test_a_well_formed_number_is_left_alone(self):
		self.assertEqual(_clean_book("A028/19"), "A028/19")

	def test_something_that_is_not_a_book_number_is_left_exactly_as_found(self):
		"""Guessing at these is how a wrong number becomes the record."""
		for raw in ("ELLA", "23:29", "", "   "):
			self.assertEqual(_clean_book(raw), raw.strip())

	def test_tidying_never_produces_a_different_animal(self):
		"""The sequence and the year must survive.

		Not the raw digits: turning the letter O into the zero it stands for
		legitimately adds one, which is the whole point of the fix.
		"""
		for raw, seq, year in (("AO63/20", "63", "20"), ("A053\\25", "053", "25"),
		                       ("A028/19", "028", "19")):
			out = _clean_book(raw)
			self.assertTrue(out.endswith("/" + year), "{} lost its year".format(raw))
			self.assertIn(seq.lstrip("0"), out, "{} lost its sequence".format(raw))


class TestBookNumbersOnAnimals(IntegrationTestCase):
	def setUp(self):
		self.booked = frappe.get_all(
			"Animal", filters=[["book_number", "is", "set"]],
			fields=["name", "book_number", "current_herd"], limit_page_length=0)
		if not self.booked:
			raise unittest.SkipTest("no book numbers on this site (demo/place_herd_inventory.py)")

	def test_they_are_well_formed(self):
		odd = [a for a in self.booked if not re.match(r"^A\d{3}/\d{2}$", a.book_number)]
		# One entry in the sheet is a name in the book-number column; it is kept
		# as found rather than invented, so at most a handful may not match.
		self.assertLessEqual(len(odd), 4, "unexpected book number shapes: {}".format(odd[:5]))

	def test_duplicates_are_known_and_few(self):
		"""A register number should identify one animal. The 26 August sheet has
		a small number that do not — reported rather than silently deduplicated,
		because deciding which animal keeps a number is the farm's call.
		"""
		seen, clashes = {}, []
		for a in self.booked:
			if not re.match(r"^A\d{3}/\d{2}$", a.book_number):
				continue
			if a.book_number in seen:
				clashes.append((a.book_number, seen[a.book_number], a.name))
			seen[a.book_number] = a.name
		self.assertLessEqual(
			len(clashes), 5,
			"more shared book numbers than expected — the register needs a look: {}".format(clashes[:5]))

	def test_it_is_a_field_not_the_document_name(self):
		"""Autonaming from it would leave the 24 animals with no book number, and
		the four malformed ones, unnameable."""
		self.assertNotEqual(frappe.get_meta("Animal").autoname, "field:book_number")


class TestHerdNameMapping(IntegrationTestCase):
	"""The inventory and the site call some herds different things."""

	def test_every_inventory_group_maps_to_a_real_herd(self):
		for group, herd in HERD.items():
			self.assertTrue(frappe.db.exists("Herds", herd),
			                "{!r} maps to {!r}, which is not a herd here".format(group, herd))

	def test_the_mapping_is_not_the_identity(self):
		"""If it were, the 186 apparent moves would have been taken literally."""
		differing = [g for g, h in HERD.items() if g != h]
		self.assertTrue(differing, "at least one herd is named differently in the inventory")

	def test_no_two_groups_map_to_one_herd(self):
		self.assertEqual(len(set(HERD.values())), len(HERD))


class TestHeadCountsAgree(IntegrationTestCase):
	def test_the_headcount_field_matches_the_live_animals(self):
		"""It used to count retired animals too, so feed was manufactured for
		cows that were dead or sold."""
		RETIRED = ["Dead", "Deceased", "Sold", "Culled", "Disposed"]
		for h in frappe.get_all("Herds", fields=["name", "number_of_animals"]):
			live = frappe.db.count("Animal", {
				"current_herd": h.name, "status": ["not in", RETIRED], "disabled": 0})
			self.assertEqual(int(h.number_of_animals or 0), live,
			                 "{}: field says {}, {} are live".format(h.name, h.number_of_animals, live))
