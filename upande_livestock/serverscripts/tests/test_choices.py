"""The dropdown builders every options endpoint shares.

`active_animals` is the one that matters: it is the single definition of which
animals are still livestock, and the dashboard, the operations block and the
mobile client must not each decide that separately. `RETIRED_STATUSES` is
asserted against the Animal doctype's own Select so the list cannot silently
fall out of step with it.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common.choices import (
	RETIRED_STATUSES,
	active_animals,
	herd_label_map,
	is_active,
	select_options,
)


class TestChoices(IntegrationTestCase):
	def test_retired_statuses_are_all_real_animal_statuses(self):
		options = frappe.get_meta("Animal").get_field("status").options.split("\n")
		for status in RETIRED_STATUSES:
			self.assertIn(status, options, f"{status} is not an Animal status")

	def test_select_options_reads_the_doctype_not_a_hardcoded_list(self):
		self.assertEqual(
			select_options("Animal", "sex"),
			[o for o in frappe.get_meta("Animal").get_field("sex").options.split("\n") if o],
		)

	def test_active_animals_excludes_every_retired_status(self):
		for row in active_animals():
			self.assertNotIn(row.get("status"), RETIRED_STATUSES)

	def test_is_active_rejects_a_retired_status(self):
		self.assertFalse(is_active({"disabled": 0, "status": RETIRED_STATUSES[0]}))

	def test_is_active_rejects_a_disabled_animal(self):
		self.assertFalse(is_active({"disabled": 1, "status": "Active"}))

	def test_is_active_accepts_a_live_animal(self):
		self.assertTrue(is_active({"disabled": 0, "status": "Active"}))

	def test_herd_label_map_covers_every_herd(self):
		self.assertEqual(len(herd_label_map()), frappe.db.count("Herds"))
