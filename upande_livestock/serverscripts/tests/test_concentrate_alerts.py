# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Telling the farm the concentrate is running out, before it does.

The only alert on this system that is not about an animal. A cow overdue for a
move is still fed tomorrow; a concentrate that runs out stops eight herds at
once, on a morning nobody chose.

Two judgements are pinned here. COVER IS COUNTED IN DAYS, because "412 kg of
calves meal" means nothing without the herd behind it — six weeks for the
calves, two days for the milkers. And "LOW" AND "OUT" ARE DIFFERENT NEWS: a
farm told "low" when the truth is "you cannot fix this by mixing" mixes, fails,
and finds out a day later.
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.alerts import _concentrate
from upande_livestock.serverscripts.alerts._shared import CATEGORY_OF_KIND, FEED_KINDS, KINDS
from upande_livestock.serverscripts.alerts.raise_alerts import already_open

PLAN = "upande_livestock.serverscripts.alerts._concentrate.concentrate_plan"


def _plan(**over):
	row = {
		"item_code": "Calves Meal", "item_name": "Calves Meal",
		"per_day_kg": 50.0, "on_hand_kg": 500.0, "days_cover": 10.0,
		"can_mix": True, "short": [], "to_mix_kg": 0.0,
	}
	row.update(over)
	return lambda *a, **k: {"ok": True, "concentrates": [row]}


class TestWhatCountsAsRunningOut(IntegrationTestCase):
	def _alerts(self, **over):
		with mock.patch(PLAN, _plan(**over)), \
		     mock.patch.object(_concentrate, "cover_days", lambda: 7.0):
			return _concentrate.concentrate_alerts()

	def test_plenty_of_cover_says_nothing(self):
		"""An alert repeated nightly is an alert people learn to skip."""
		self.assertEqual(self._alerts(days_cover=10.0), [])

	def test_thin_cover_asks_for_a_batch(self):
		got = self._alerts(days_cover=3.0, on_hand_kg=150.0)
		self.assertEqual(len(got), 1)
		self.assertEqual(got[0]["kind"], "Concentrate Low")
		self.assertIn("3 days left", got[0]["message"])
		self.assertIn("Mix a batch", got[0]["message"])

	def test_an_empty_bin_is_a_different_kind_of_news(self):
		got = self._alerts(on_hand_kg=0.0, days_cover=0.0)
		self.assertEqual(got[0]["kind"], "Concentrate Out")

	def test_what_cannot_be_mixed_names_the_missing_material(self):
		"""'Cannot mix' sends someone to the store. Naming it sends them to the
		supplier, which is the only thing that fixes it."""
		got = self._alerts(can_mix=False, short=[{"item_code": "4040010020"}])
		self.assertEqual(got[0]["kind"], "Concentrate Out")
		self.assertIn("has to be bought", got[0]["message"])
		self.assertIn("Wheat Bran", got[0]["message"])

	def test_a_full_bin_that_cannot_be_remixed_is_still_out(self):
		"""Stock in hand is no comfort when the next batch is impossible."""
		got = self._alerts(on_hand_kg=800.0, days_cover=16.0, can_mix=False,
		                   short=[{"item_code": "4040010020"}])
		self.assertEqual(got[0]["kind"], "Concentrate Out")

	def test_a_concentrate_nothing_eats_cannot_run_out(self):
		"""No herd on it means no such thing as running out."""
		self.assertEqual(self._alerts(per_day_kg=0.0, on_hand_kg=0.0), [])

	def test_a_threshold_of_zero_turns_the_check_off(self):
		with mock.patch(PLAN, _plan(days_cover=0.5, on_hand_kg=10.0)), \
		     mock.patch.object(_concentrate, "cover_days", lambda: 0.0):
			self.assertEqual(_concentrate.concentrate_alerts(), [])


class TestTheseAlertsAreAboutAFeedNotAnAnimal(IntegrationTestCase):
	def test_the_kinds_are_registered_and_filed_under_feed(self):
		"""A kind added in one place and not the other is a silently uncounted
		alert — the reason _shared.py exists."""
		for kind in FEED_KINDS:
			self.assertIn(kind, KINDS)
			self.assertEqual(CATEGORY_OF_KIND[kind], "feed")

	def test_two_short_concentrates_are_two_alerts(self):
		"""Keyed on the item. Keyed on the animal — which is None for both —
		the first would suppress the second and the farm would hear about one
		empty bin out of four."""
		frappe.db.delete("Livestock Alert", {"alert_kind": "Concentrate Low"})
		for item in ("Calves Meal", "Weaner Meal"):
			doc = frappe.new_doc("Livestock Alert")
			doc.alert_kind = "Concentrate Low"
			doc.alert_date = frappe.utils.today()
			doc.item = item
			doc.message = f"{item} is low"
			doc.insert(ignore_permissions=True)

		self.assertTrue(already_open("Concentrate Low", None, "Calves Meal"))
		self.assertTrue(already_open("Concentrate Low", None, "Weaner Meal"))
		self.assertFalse(already_open("Concentrate Low", None, "Dry Cows  Meal"))

	def test_an_animal_alert_is_still_keyed_on_the_animal(self):
		"""The item key must not have changed what the other six do."""
		frappe.db.delete("Livestock Alert", {"alert_kind": "Move Due"})
		animal = frappe.db.get_value("Animal", {"disabled": 0}, "name")
		doc = frappe.new_doc("Livestock Alert")
		doc.alert_kind = "Move Due"
		doc.alert_date = frappe.utils.today()
		doc.animal = animal
		doc.message = "test"
		doc.insert(ignore_permissions=True)
		self.assertTrue(already_open("Move Due", animal))
		self.assertFalse(already_open("Move Due", "NO-SUCH-ANIMAL"))
