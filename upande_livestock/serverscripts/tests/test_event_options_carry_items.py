"""The options an event screen loads carry what each event type may use.

One endpoint serves several screens (breeding: service, diagnosis, heat, drying
off), so a single `items` key cannot say which screen's list it is. The map is
keyed by event type and covers every type set to post stock, so a page has its
picker list the moment it loads; it is built by the lookup every other picker
uses.
"""

import unittest
from unittest.mock import patch

from upande_livestock.serverscripts.breeding import breeding_options as BO
from upande_livestock.serverscripts.common import event_items as EI
from upande_livestock.serverscripts.health import health_options as HO
from upande_livestock.serverscripts.movement import event_options as EO

TYPES = ("Service", "Heat Detection", "Pregnancy Diagnosis", "Drying Off", "Abortion", "Calving", "Check Up")
SCREENS = ((BO, "breeding_options"), (HO, "health_options"), (EO, "event_options"))


def _fake(event_type, company=None):
	return [{"value": f"ITEM-{event_type}", "item_name": event_type}]


def _map(mod, fn, items=_fake, consumes=lambda t: True):
	with patch.object(EI, "_rules", return_value={t: {"posts": True, "groups": [], "default_store": None, "must_name_item": False} for t in TYPES}), \
	     patch.object(EI, "items_for_event", side_effect=items), \
	     patch.object(EI, "consumes_items", side_effect=consumes):
		out = getattr(mod, fn)()
	assert out.get("ok"), out
	return out["items_by_event"]


class TestOptionsCarryItemsByEvent(unittest.TestCase):
	def test_every_screen_carries_every_posting_type(self):
		for mod, fn in SCREENS:
			m = _map(mod, fn)
			self.assertEqual(set(m), set(TYPES), fn)
			self.assertEqual(m["Drying Off"][0]["value"], "ITEM-Drying Off", fn)

	def test_breeding_carries_drying_off_and_diagnosis(self):
		m = _map(BO, "breeding_options")
		self.assertEqual(m["Drying Off"][0]["value"], "ITEM-Drying Off")
		self.assertEqual(m["Pregnancy Diagnosis"][0]["value"], "ITEM-Pregnancy Diagnosis")

	def test_health_carries_check_up(self):
		self.assertEqual(_map(HO, "health_options")["Check Up"][0]["value"], "ITEM-Check Up")

	def test_an_unmapped_type_has_no_key_at_all(self):
		"""Absent, not []: the screen reads absent as "not set to post stock",
		and [] as "set, but nothing in stock"."""
		for mod, fn in SCREENS:
			self.assertEqual(_map(mod, fn, items=lambda t, c=None: [], consumes=lambda t: False), {}, fn)

	def test_a_mapped_type_with_nothing_in_stock_keeps_an_empty_list(self):
		m = _map(BO, "breeding_options", items=lambda t, c=None: [], consumes=lambda t: t == "Heat Detection")
		self.assertEqual(m, {"Heat Detection": []})

	def test_service_is_omitted_when_it_posts_nothing(self):
		"""Absent Service key is what keeps the legacy straw picker on screen."""
		self.assertEqual(list(_map(BO, "breeding_options", consumes=lambda t: t == "Service")), ["Service"])
		self.assertNotIn("Service", _map(BO, "breeding_options", consumes=lambda t: t != "Service"))
