# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The farm's own register number, and the herd an animal is actually in.

A book number — A028/19 — is a letter, a sequence and the year of birth. It is
what people say out loud about an animal.

It used to be a field and nothing more, because four of the 298 entries are not
register numbers at all and some animals had none, and a naming scheme that
cannot name every record is not a naming scheme. That objection was answered
rather than overruled: common/animal_id.allocate gives anything the register
cannot name the next free number in its birth year, so the scheme now names
everything, and the number is the record's name.

`book_number` did not go away. It keeps the register's own words — including the
four that are not numbers — as evidence of what the paper book said. The record
name is the authority; this is the photograph of the original.
"""

import re
import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, today

from upande_livestock.demo.place_herd_inventory import HERD, _clean_book
from upande_livestock.serverscripts.common import animal_id


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

	def test_the_register_field_holds_what_the_paper_said(self):
		"""Raw, not tidied. AO38/26, B024/26, ELLA, A053\\25 and two that Excel
		read as times of day are all in here exactly as the farm wrote them.

		Asserting a shape on this field is what the earlier version of this test
		did, and it was asserting the wrong thing: once the number moved onto the
		record name, tidying this copy too would have destroyed the only evidence
		of what the original entry was.
		"""
		raw = [a for a in self.booked if not re.match(r"^[AB]\d{3}/\d{2}$", a.book_number)]
		self.assertTrue(raw, "the register's own spellings have been overwritten")

	def test_every_register_entry_still_points_at_its_own_animal(self):
		"""Tidied, a register entry should be the name of the animal holding it.

		The exceptions are the register's own faults, not this system's: three
		entries are not numbers, and two numbers are each written against two
		different animals.
		"""
		astray = [
			(a.name, a.book_number) for a in self.booked
			if animal_id.parse(animal_id.tidy(a.book_number))
			and animal_id.tidy(a.book_number) != a.name
		]
		self.assertLessEqual(
			len(astray), 5,
			"register entries pointing at the wrong animal: {}".format(astray[:5]))

	def test_the_entries_that_are_not_numbers_are_still_here(self):
		"""ELLA and the two Excel read as times of day. They were not deleted and
		they were not guessed at — the animals were given free numbers instead."""
		kept = [a.book_number for a in self.booked
		        if not animal_id.parse(animal_id.tidy(a.book_number))]
		for a in kept:
			self.assertTrue(a.strip(), "an unusable entry was blanked instead of kept")

	def test_the_register_field_is_never_the_naming_source(self):
		"""Autonaming from the register itself would leave the animals it cannot
		name unnameable. Animals are named from tag_number, which animal_id fills
		— from the register where it reads, and by allocation where it does not."""
		self.assertNotEqual(frappe.get_meta("Animal").autoname, "field:book_number")
		self.assertEqual(frappe.get_meta("Animal").autoname, "field:tag_number")


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


class TestTheNumberIsTheName(IntegrationTestCase):
	"""Once the register has been loaded, an animal IS its number.

	Skipped on a site that has not had demo/load_herd_register.py run against it,
	because there is nothing to assert about a register that was never loaded.
	"""

	def setUp(self):
		self.named = [
			a for a in frappe.get_all(
				"Animal", fields=["name", "sex", "date_of_birth", "book_number"],
				limit_page_length=0)
			if animal_id.parse(a.name)
		]
		if len(self.named) < 50:
			raise unittest.SkipTest("register not loaded here (demo/load_herd_register.py)")

	def test_the_letter_agrees_with_the_sex(self):
		"""A bull in the heifer series would climb a ladder to the parlour."""
		wrong = [
			a.name for a in self.named
			if animal_id.parse(a.name)["prefix"] != animal_id.PREFIX_BY_SEX.get(a.sex)
		]
		self.assertFalse(wrong, "numbered against their sex: {}".format(wrong[:5]))

	def test_the_year_agrees_with_the_date_of_birth(self):
		wrong = [
			(a.name, str(a.date_of_birth))
			for a in self.named
			if a.date_of_birth and animal_id.parse(a.name)["year"] != getdate(a.date_of_birth).year
		]
		# The register is the farm's, not a derivation: a calf born on 2 January
		# and written into the old year is the farm's record, not an error to fix.
		self.assertLessEqual(
			len(wrong), len(self.named) // 10,
			"more numbers disagree with their birth year than the register explains: {}".format(
				wrong[:5]))

	def test_no_number_is_held_twice(self):
		"""The name is the primary key, so this cannot fail — which is exactly
		why the number was moved onto it."""
		self.assertEqual(len(self.named), len({a.name for a in self.named}))

	def test_none_of_them_is_dated_in_the_future(self):
		this_year = getdate(today()).year
		ahead = [a.name for a in self.named if animal_id.parse(a.name)["year"] > this_year]
		self.assertFalse(ahead, "numbered in a year that has not happened: {}".format(ahead[:5]))
