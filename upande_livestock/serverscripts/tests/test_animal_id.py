# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""An animal's number: what it looks like, and who may hold it.

A039/26 is the thirty-ninth heifer born in 2026. B013/26 is a bull born the same
year — a different series, not a later entry in the same one, which is why the
farm's register runs B013/26 through B024/26 alongside A002/26 through A039/26.

Every refusal here is tested for what it TELLS the user, not only that it
refuses. Somebody correcting a number by hand needs to be told which ones are
free; "Validation Error" sends them back to the paper book.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, today

from upande_livestock.serverscripts.common import animal_id


def _kill(name):
	if frappe.db.exists("Animal", name):
		frappe.delete_doc("Animal", name, force=True, ignore_permissions=True)


def _animal(name, sex="Female", dob=None):
	"""An animal that exists only to occupy a number."""
	_kill(name)
	doc = frappe.get_doc({
		"doctype": "Animal",
		"tag_number": name,
		"burn_name": name.replace("/", "-"),
		"sex": sex,
		"status": "Active",
		"date_of_birth": dob or today(),
	}).insert(ignore_permissions=True)
	return doc


class TestTheGrammar(IntegrationTestCase):
	def test_a_number_parses_into_its_three_parts(self):
		got = animal_id.parse("A039/26")
		self.assertEqual((got["prefix"], got["seq"], got["yy"], got["year"]),
		                 ("A", 39, 26, 2026))

	def test_a_bull_parses_the_same_way(self):
		got = animal_id.parse("B013/26")
		self.assertEqual((got["prefix"], got["seq"], got["year"]), ("B", 13, 2026))

	def test_the_year_is_the_year_of_birth_not_the_century(self):
		self.assertEqual(animal_id.parse("A028/19")["year"], 2019)

	def test_what_is_not_a_number_parses_to_nothing(self):
		for raw in ("ELLA", "23:29", "", None, "A39/26", "A0392/6", "C013/26", "A013-26"):
			self.assertIsNone(animal_id.parse(raw), "{!r} should not parse".format(raw))

	def test_formatting_pads_the_sequence(self):
		self.assertEqual(animal_id.format_id("A", 9, 26), "A009/26")
		self.assertEqual(animal_id.format_id("B", 130, 5), "B130/05")

	def test_format_and_parse_are_inverses(self):
		for prefix in ("A", "B"):
			for seq in (1, 9, 10, 99, 100, 999):
				for yy in (0, 19, 26, 99):
					out = animal_id.format_id(prefix, seq, yy)
					got = animal_id.parse(out)
					self.assertEqual((got["prefix"], got["seq"], got["yy"]), (prefix, seq, yy))


class TestSexDecidesTheLetter(IntegrationTestCase):
	def test_a_heifer_is_an_a(self):
		self.assertEqual(animal_id.prefix_for_sex("Female"), "A")

	def test_a_bull_is_a_b(self):
		self.assertEqual(animal_id.prefix_for_sex("Male"), "B")

	def test_case_and_spacing_do_not_matter(self):
		self.assertEqual(animal_id.prefix_for_sex(" female "), "A")
		self.assertEqual(animal_id.prefix_for_sex("MALE"), "B")

	def test_a_missing_sex_is_refused_rather_than_assumed(self):
		"""Defaulting to A would number a bull calf as a heifer and put him on
		the ladder to the milking parlour."""
		for bad in (None, "", "Unknown"):
			with self.assertRaises(frappe.ValidationError):
				animal_id.prefix_for_sex(bad)


class TestTidyingTheRegister(IntegrationTestCase):
	"""Two transcription habits run through the sheet. Neither invents a number."""

	def test_a_letter_o_becomes_the_zero_it_was_meant_to_be(self):
		self.assertEqual(animal_id.tidy("AO63/20"), "A063/20")
		self.assertEqual(animal_id.tidy("Ao63/20"), "A063/20")

	def test_a_bull_gets_the_same_treatment(self):
		self.assertEqual(animal_id.tidy("BO13/26"), "B013/26")

	def test_a_backslash_becomes_the_separator(self):
		self.assertEqual(animal_id.tidy("A053\\25"), "A053/25")

	def test_a_well_formed_number_is_left_alone(self):
		self.assertEqual(animal_id.tidy("A028/19"), "A028/19")
		self.assertEqual(animal_id.tidy("B013/26"), "B013/26")

	def test_a_zero_typed_as_o_twice_is_still_two_zeroes(self):
		"""BOO9/26 is B009/26. The habit is "type O for zero", not a rule about
		which position the O falls in."""
		self.assertEqual(animal_id.tidy("BOO9/26"), "B009/26")
		self.assertEqual(animal_id.tidy("AOO5/25"), "A005/25")

	def test_something_that_is_not_a_number_is_left_exactly_as_found(self):
		"""Guessing at these is how a wrong number becomes the record."""
		for raw in ("ELLA", "23:29", "", "   "):
			self.assertEqual(animal_id.tidy(raw), raw.strip())

	def test_tidying_never_changes_which_animal_is_meant(self):
		for raw, seq, year in (("AO63/20", "63", "20"), ("A053\\25", "053", "25"),
		                       ("A028/19", "028", "19")):
			out = animal_id.tidy(raw)
			self.assertTrue(out.endswith("/" + year), "{} lost its year".format(raw))
			self.assertIn(seq.lstrip("0"), out, "{} lost its sequence".format(raw))


class TestTheTwoSeriesAreIndependent(IntegrationTestCase):
	"""The register proves it: B013/26 and A039/26 are both the real thing."""

	def setUp(self):
		self.made = []
		for name, sex in (("A901/26", "Female"), ("A902/26", "Female"), ("B901/26", "Male")):
			_animal(name, sex)
			self.made.append(name)
		self.addCleanup(lambda: [_kill(n) for n in self.made])

	def test_a_heifer_number_does_not_occupy_the_bull_series(self):
		self.assertIn(901, animal_id.taken("A", 26))
		self.assertIn(901, animal_id.taken("B", 26))
		self.assertNotIn(902, animal_id.taken("B", 26))

	def test_a_year_does_not_see_another_year(self):
		self.assertNotIn(901, animal_id.taken("A", 25))


class TestWhatTheNextNumberIs(IntegrationTestCase):
	def setUp(self):
		self.used = {3, 4, 7, 12}

	def test_it_is_one_past_the_high_water_mark_not_the_lowest_hole(self):
		"""A calf born today is the next one in the book. The holes are a
		different question, asked when somebody corrects a number by hand."""
		self.assertEqual(animal_id.next_free("A", 26, used=self.used), 13)

	def test_an_empty_year_starts_at_one(self):
		self.assertEqual(animal_id.next_free("A", 26, used=set()), 1)

	def test_the_holes_are_the_ones_below_the_mark(self):
		self.assertEqual(animal_id.gaps("A", 26, used=self.used), [1, 2, 5, 6, 8, 9, 10, 11])

	def test_an_empty_year_has_no_holes_only_open_road(self):
		self.assertEqual(animal_id.gaps("A", 26, used=set()), [])

	def test_the_holes_are_capped_so_the_message_stays_readable(self):
		self.assertEqual(len(animal_id.gaps("A", 26, limit=3, used=self.used)), 3)

	def test_runs_are_collapsed_for_a_human_to_read(self):
		self.assertEqual(animal_id.describe_gaps("A", 26, used=self.used),
		                 "001-002, 005-006, 008-011")

	def test_a_lone_hole_is_not_written_as_a_run(self):
		self.assertEqual(animal_id.describe_gaps("A", 26, used={1, 3}), "002")


class TestAllocation(IntegrationTestCase):
	def setUp(self):
		self.made = []
		self.addCleanup(lambda: [_kill(n) for n in self.made])

	def _hold(self, name, sex):
		_animal(name, sex)
		self.made.append(name)

	def test_it_uses_the_birth_year_not_this_year(self):
		got = animal_id.parse(animal_id.allocate("Female", "2024-03-04"))
		self.assertEqual(got["year"], 2024)

	def test_the_sex_decides_the_letter(self):
		self.assertTrue(animal_id.allocate("Male", today()).startswith("B"))
		self.assertTrue(animal_id.allocate("Female", today()).startswith("A"))

	def test_it_steps_past_what_is_already_there(self):
		yy = getdate(today()).year % 100
		first = animal_id.allocate("Female", today())
		self._hold(first, "Female")
		second = animal_id.allocate("Female", today())
		self.assertGreater(animal_id.parse(second)["seq"], animal_id.parse(first)["seq"])
		self.assertEqual(animal_id.parse(second)["yy"], yy)

	def test_what_it_hands_out_is_free(self):
		self.assertFalse(frappe.db.exists("Animal", animal_id.allocate("Female", today())))


class TestWhoMayHoldANumber(IntegrationTestCase):
	def setUp(self):
		self.taken_id = "A903/26"
		_animal(self.taken_id, "Female")
		self.addCleanup(lambda: _kill(self.taken_id))

	def test_a_shape_that_is_not_a_number_is_refused_with_an_example(self):
		with self.assertRaises(frappe.ValidationError) as cm:
			animal_id.assert_assignable("ELLA", "Female")
		self.assertIn("A013/26", str(cm.exception))

	def test_a_letter_that_contradicts_the_sex_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as cm:
			animal_id.assert_assignable("B013/26", "Female")
		self.assertIn("B", str(cm.exception))

	def test_a_year_that_has_not_happened_is_refused(self):
		"""'you cannot backdate a future event' — in the farm's own words."""
		nxt = (getdate(today()).year + 1) % 100
		with self.assertRaises(frappe.ValidationError) as cm:
			animal_id.assert_assignable(animal_id.format_id("A", 5, nxt), "Female")
		self.assertIn(str(getdate(today()).year + 1), str(cm.exception))

	def test_this_year_is_allowed(self):
		yy = getdate(today()).year % 100
		animal_id.assert_assignable(animal_id.format_id("A", 904, yy), "Female")

	def test_a_number_someone_else_holds_is_refused_and_names_them(self):
		with self.assertRaises(frappe.ValidationError) as cm:
			animal_id.assert_assignable(self.taken_id, "Female")
		self.assertIn(self.taken_id, str(cm.exception))

	def test_the_refusal_offers_the_free_numbers(self):
		"""'if number 13 is already picked ... suggest a list of numbers that is
		present in between the list'."""
		with self.assertRaises(frappe.ValidationError) as cm:
			animal_id.assert_assignable(self.taken_id, "Female")
		self.assertIn("Free in 2026", str(cm.exception))

	def test_keeping_the_number_it_already_has_is_not_a_clash(self):
		animal_id.assert_assignable(self.taken_id, "Female", current=self.taken_id)

	def test_a_valid_free_number_returns_its_parts(self):
		got = animal_id.assert_assignable("A905/26", "Female")
		self.assertEqual(got["seq"], 905)


class TestANumberWrittenIntoAName(IntegrationTestCase):
	"""Ten animals here have no register field but carry a number in their
	display name, typed there because there was nowhere else to put it."""

	def test_it_is_read_back_out(self):
		self.assertEqual(animal_id.extract("BO05/26 (Bull)"), "B005/26")
		self.assertEqual(animal_id.extract("AO06/26 (Cow)"), "A006/26")
		self.assertEqual(animal_id.extract("AO78/25"), "A078/25")

	def test_it_is_tidied_on_the_way_out(self):
		self.assertEqual(animal_id.extract("BOO9/26 (Bull)"), "B009/26")

	def test_a_name_with_no_number_in_it_yields_nothing(self):
		for text in ("MEMO", "herd-210662", "", None, "W.311/8410", "YULIA/8406"):
			self.assertEqual(animal_id.extract(text), "", "{!r} should yield nothing".format(text))

	def test_it_will_not_take_a_fragment_out_of_a_longer_token(self):
		"""Reading a number out of the middle of something else is guessing."""
		self.assertEqual(animal_id.extract("XA013/26"), "")
		self.assertEqual(animal_id.extract("B013/267"), "")
