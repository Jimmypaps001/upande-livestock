"""The options an event screen loads carry what each of ITS event types may use.

One endpoint serves several screens (breeding: service, diagnosis, heat), so a
single `items` key cannot say which screen's list it is. The map is keyed by
event type, and is built by the lookup every other picker uses.
"""

import unittest
from unittest.mock import patch

from upande_livestock.serverscripts.breeding import breeding_options as BO
from upande_livestock.serverscripts.health import health_options as HO
from upande_livestock.serverscripts.movement import event_options as EO


def _fake(event_type, company=None):
	return [{"value": f"ITEM-{event_type}", "item_name": event_type}]


class TestOptionsCarryItemsByEvent(unittest.TestCase):
	def _items(self, mod, fn):
		with patch.object(mod, "items_for_event", side_effect=_fake, create=True), \
		     patch.object(mod, "consumes_items", return_value=True, create=True):
			out = getattr(mod, fn)()
		self.assertTrue(out.get("ok"), out)
		return out["items_by_event"]

	def test_breeding_carries_heat_and_diagnosis(self):
		m = self._items(BO, "breeding_options")
		self.assertEqual(m["Heat Detection"][0]["value"], "ITEM-Heat Detection")
		self.assertEqual(m["Pregnancy Diagnosis"][0]["value"], "ITEM-Pregnancy Diagnosis")

	def test_health_carries_abortion(self):
		m = self._items(HO, "health_options")
		self.assertEqual(m["Abortion"][0]["value"], "ITEM-Abortion")

	def test_movement_options_carry_calving(self):
		m = self._items(EO, "event_options")
		self.assertEqual(m["Calving"][0]["value"], "ITEM-Calving")

	def test_an_unmapped_type_has_no_key_at_all(self):
		"""Absent, not []: the screen reads absent as "not configured, show
		nothing", and [] as "mapped, but nothing in stock"."""
		for mod, fn in ((BO, "breeding_options"), (HO, "health_options"), (EO, "event_options")):
			with patch.object(mod, "items_for_event", return_value=[], create=True), \
			     patch.object(mod, "consumes_items", return_value=False, create=True):
				m = getattr(mod, fn)()["items_by_event"]
			self.assertEqual(m, {}, fn)

	def test_a_mapped_type_with_nothing_in_stock_keeps_an_empty_list(self):
		with patch.object(BO, "items_for_event", return_value=[], create=True), \
		     patch.object(BO, "consumes_items", side_effect=lambda t: t == "Heat Detection", create=True):
			m = BO.breeding_options()["items_by_event"]
		self.assertEqual(m, {"Heat Detection": []})
