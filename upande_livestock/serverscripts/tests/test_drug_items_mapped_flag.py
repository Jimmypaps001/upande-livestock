"""A loaded `drug_items` of [] is ambiguous: unmapped, or mapped but unstocked.

Treatment and Husbandry send the list bare, so each also says whether anything
is mapped — the screen words the two cases differently, and only the farm that
has not mapped anything should be pointed at Settings.
"""

import unittest
from unittest.mock import patch

from upande_livestock.serverscripts.health import open_health_cases as OHC
from upande_livestock.serverscripts.husbandry import _shared
from upande_livestock.serverscripts.husbandry import drugs_in_store as DIS
from upande_livestock.serverscripts.husbandry import husbandry_options as HO

CE = "upande_livestock.serverscripts.common.event_items.groups_for_event"


class TestTreatment(unittest.TestCase):
	def _call(self, mapped):
		with patch.object(OHC, "items_for_event", return_value=[]), \
		     patch.object(OHC, "consumes_items", return_value=mapped, create=True):
			return OHC.open_health_cases()

	def test_unmapped(self):
		self.assertIs(self._call(False)["drug_items_mapped"], False)

	def test_mapped_but_unstocked(self):
		out = self._call(True)
		self.assertIs(out["drug_items_mapped"], True)
		self.assertEqual(out["drug_items"], [])


class TestHusbandry(unittest.TestCase):
	def test_unmapped_when_no_husbandry_type_is_mapped(self):
		with patch(CE, return_value=[]):
			self.assertFalse(_shared.husbandry_items_mapped())

	def test_mapped_when_any_husbandry_type_is(self):
		with patch(CE, side_effect=lambda t: ["Drugs"] if t == "Dehorning" else []):
			self.assertTrue(_shared.husbandry_items_mapped())

	def test_both_husbandry_endpoints_carry_it(self):
		for mod, fn in ((HO, "husbandry_options"), (DIS, "drugs_in_store")):
			with patch.object(mod, "husbandry_items_mapped", return_value=False, create=True):
				out = getattr(mod, fn)()
			self.assertIs(out["drug_items_mapped"], False, fn)
