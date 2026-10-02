"""Service takes the general table only where a straws-only group exists.

On live the straws sit in a group beside hundreds of items that are not straws,
so mapping Service there would offer all of them — a picker worse than the one it
has. The rule is evaluated per site, from the mapping, so no release decides it:
kaitet.local has a `Dairy Semen` group and a `Service -> Dairy Semen` row, live
has neither, and the same code serves both.
"""

import unittest
from unittest.mock import patch

from upande_livestock.serverscripts.common import event_items as EI


class TestTheRuleIsPerSite(unittest.TestCase):
	def test_a_site_with_no_service_mapping_keeps_the_legacy_fields(self):
		"""Live's shape: Service unmapped, so it keeps `semen_item`."""
		with patch.object(
			EI,
			"_mapping_rows",
			return_value=[{"event_type": "Vaccination", "item_group": "Dairy Drugs"}],
		):
			self.assertFalse(EI.consumes_items("Service"))
			self.assertEqual(EI.groups_for_event("Service"), [])

	def test_a_site_that_mapped_service_uses_the_table(self):
		"""kaitet.local's shape: Service mapped, so it takes the general table."""
		with patch.object(
			EI,
			"_mapping_rows",
			return_value=[{"event_type": "Service", "item_group": "Dairy Semen"}],
		):
			self.assertTrue(EI.consumes_items("Service"))
			self.assertEqual(EI.groups_for_event("Service"), ["Dairy Semen"])

	def test_one_event_type_can_hold_as_many_groups_as_the_farm_needs(self):
		"""The mapping is a list, not a pair of slots: 1, 2, 4 or 7 rows all work."""
		with patch.object(
			EI,
			"_mapping_rows",
			return_value=[
				{"event_type": "Service", "item_group": "Dairy Semen"},
				{"event_type": "Service", "item_group": "Dairy Sundries"},
				{"event_type": "Service", "item_group": "Dairy Hormones"},
			],
		):
			self.assertEqual(
				EI.groups_for_event("Service"),
				["Dairy Semen", "Dairy Sundries", "Dairy Hormones"],
			)
