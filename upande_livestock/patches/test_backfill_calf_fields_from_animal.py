# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import ensure_livestock_event_types
from upande_livestock.patches.backfill_calf_fields_from_animal import execute


def _delete_and_commit(doctype, name):
	frappe.db.delete(doctype, {"name": name})
	frappe.db.commit()


def make_animal(tag, sex="Female"):
	if frappe.db.exists("Animal", tag):
		return frappe.get_doc("Animal", tag)
	return frappe.get_doc(
		{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": sex, "status": "Active"}
	).insert()


class TestBackfillCalfFieldsFromAnimal(IntegrationTestCase):
	"""Drive the patch against throwaway Birth events, not just real kaitet.local
	data: asserting "every Birth event has calf fields" would be hollow once the
	patch has run for real, since that would stay true forever and pass against
	a stubbed `execute(): pass`. Each test here creates its own event starting
	from a blank/mismatched state, so a stub fails.

	A fixture Birth event with `animal` set and no calf_tag_number/calf_sex can
	no longer be built with a plain insert() — Step 5c's own validate() check
	(the thing this patch exists to unblock) would reject it immediately.
	flags.ignore_validate reproduces "submitted before the fields existed"
	without fighting the very check being tested around.
	"""

	def setUp(self):
		ensure_livestock_event_types()
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def _birth_event(self, calf, calf_tag_number=None, calf_sex=None, is_stillborn=0):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Birth",
				"event_date": "2026-05-01",
				"operator": self.operator,
				"animal": calf,
				"calf_tag_number": calf_tag_number,
				"calf_sex": calf_sex,
				"is_stillborn": is_stillborn,
			}
		)
		doc.flags.ignore_validate = True
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		return doc

	def test_fills_blank_calf_fields_from_the_animal(self):
		calf = make_animal("TEST-CALFBACKFILL-1", sex="Male").name
		self.addCleanup(_delete_and_commit, "Animal", calf)
		event = self._birth_event(calf)
		self.assertFalse(event.calf_tag_number)
		self.assertFalse(event.calf_sex)

		execute()

		event.reload()
		self.assertEqual(event.calf_tag_number, "TEST-CALFBACKFILL-1")
		self.assertEqual(event.calf_sex, "Male")

	def test_fills_only_the_blank_field_when_one_is_already_set(self):
		calf = make_animal("TEST-CALFBACKFILL-2", sex="Female").name
		self.addCleanup(_delete_and_commit, "Animal", calf)
		event = self._birth_event(calf, calf_tag_number="TEST-CALFBACKFILL-2")

		execute()

		event.reload()
		self.assertEqual(event.calf_tag_number, "TEST-CALFBACKFILL-2")
		self.assertEqual(event.calf_sex, "Female")

	def test_a_mismatched_tag_number_is_left_untouched(self):
		"""calf_tag_number already differs from the Animal's — leave it, don't
		silently normalise it. This is the negative case for "only fill blanks":
		a stub would trivially "pass" this too, since it never overwrites
		anything, so the assertion that matters is that calf_sex still gets
		filled independently.
		"""
		calf = make_animal("TEST-CALFBACKFILL-3", sex="Male").name
		self.addCleanup(_delete_and_commit, "Animal", calf)
		event = self._birth_event(calf, calf_tag_number="SOME-OTHER-TAG")

		execute()

		event.reload()
		self.assertEqual(event.calf_tag_number, "SOME-OTHER-TAG")
		self.assertEqual(event.calf_sex, "Male")

	def test_invalid_animal_sex_is_skipped_and_leaves_calf_sex_blank(self):
		"""Writing anything other than Female/Male into calf_sex would just
		recreate the failure Step 5c's validate() raises — the row must be
		skipped, not half-fixed.
		"""
		calf = make_animal("TEST-CALFBACKFILL-4", sex="Female").name
		self.addCleanup(_delete_and_commit, "Animal", calf)
		# Force an invalid sex directly in the DB — the Animal doctype's own
		# Select validation would reject this through a normal save.
		frappe.db.set_value("Animal", calf, "sex", "Unknown", update_modified=False)
		frappe.db.commit()
		event = self._birth_event(calf)

		execute()

		event.reload()
		self.assertFalse(event.calf_sex)
		# calf_tag_number is independently fillable (the Animal has a real tag),
		# but nothing is written for this row at all: a half-filled row would
		# still fail validate(), so the patch skips it wholesale rather than
		# leaving a partially-backfilled event behind.
		self.assertFalse(event.calf_tag_number)

	def test_stillborn_events_are_left_alone(self):
		calf = make_animal("TEST-CALFBACKFILL-5", sex="Male").name
		self.addCleanup(_delete_and_commit, "Animal", calf)
		event = self._birth_event(calf, is_stillborn=1)

		execute()

		event.reload()
		self.assertFalse(event.calf_tag_number)
		self.assertFalse(event.calf_sex)

	def test_events_with_no_animal_are_left_alone(self):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Birth",
				"event_date": "2026-05-01",
				"operator": self.operator,
				"is_stillborn": 1,
			}
		)
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)

		execute()  # must not throw looking up a blank Animal link

		doc.reload()
		self.assertFalse(doc.animal)
		self.assertFalse(doc.calf_tag_number)

	def test_patch_is_idempotent(self):
		calf = make_animal("TEST-CALFBACKFILL-6", sex="Female").name
		self.addCleanup(_delete_and_commit, "Animal", calf)
		event = self._birth_event(calf)

		execute()
		event.reload()
		once = (event.calf_tag_number, event.calf_sex)

		execute()
		event.reload()
		self.assertEqual((event.calf_tag_number, event.calf_sex), once)
