# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the farm will need, as the herds change under it.

THE HERD IS NOT A CONSTANT. Today's draw times thirty days assumes the calves
in the 0-2 pen are still there next month — they are not, they will have aged
into 2-4 — and that the cows in the milking herd are still milking, which the
ones calving in a fortnight are not. Feed is bought on a lead time, so the
number worth having is what the herd will look like when the feed arrives.

The case that prompted this, and the one these tests are built around: TWO COWS
ABORT. Their pregnancies stop being confirmed, so no calving is scheduled, no
calf arrives in the calf pen and the dams never leave the milking herd. The
forecast for the calf pen falls and the milking draw stays up — scenario B
instead of scenario A — and nobody edited a forecast, because the forecast is
not a document. It is read from the events every time it is asked for.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import herd_movement as hm
from upande_livestock.serverscripts.feeding.feed_forecast import feed_forecast
from upande_livestock.serverscripts.tests.test_culling import _employee, _tidy
from upande_livestock.serverscripts.tests.test_lactation_moves import _confirmed_service
from upande_livestock.serverscripts.tests.test_operations import _make_cow

COW = "FORECAST-DAM-1"


def _draw_for(result, item):
	for row in result["items"]:
		if row["item_code"] == item:
			return row
	return None


def _calf_ration_item():
	"""The feed the calf pen eats, whatever this farm calls it."""
	pen = hm.calf_herd("Female")
	bom = frappe.db.get_value("Herds", pen, "bom") if pen else None
	if not bom:
		return None, None
	row = frappe.get_all("BOM Item", filters={"parent": bom}, fields=["item_code"], limit=1)
	return pen, (row[0].item_code if row else None)


class TestTheHerdMovesUnderTheForecast(IntegrationTestCase):
	def test_it_says_what_it_rests_on(self):
		got = feed_forecast({"days": 30})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertIn("growth ladder", got["basis"])

	def test_the_draw_is_not_the_same_number_in_two_months(self):
		"""Which is the whole reason this exists beside the flat projection: a
		calf pen empties as its calves age out, and nothing refills it unless
		somebody is carrying."""
		got = feed_forecast({"days": 60})
		self.assertTrue(any(abs(r["drift"]) > 0.001 for r in got["items"]),
		                "no feed's draw changes over sixty days — the ladder is not moving")

	def test_calves_ageing_out_are_scheduled(self):
		got = feed_forecast({"days": 90})
		kinds = {w["kind"] for e in got["events"] for w in e["what"]}
		self.assertIn("move", kinds)

	def test_a_day_has_a_number_for_every_day_asked_for(self):
		got = feed_forecast({"days": 14})
		self.assertEqual(len(got["dates"]), 15)
		for row in got["items"]:
			self.assertEqual(len(row["series"]), 15)
			self.assertEqual(len(row["remaining"]), 15)

	def test_stock_left_never_goes_negative(self):
		"""A store stops; it does not go below nothing."""
		for row in feed_forecast({"days": 60})["items"]:
			self.assertTrue(all(v >= 0 for v in row["remaining"]))

	def test_it_writes_nothing(self):
		before = frappe.db.count("Livestock Event")
		feed_forecast({"days": 30})
		self.assertEqual(frappe.db.count("Livestock Event"), before)


class TestAPregnancyChangesTheForecastAndAnAbortionChangesItBack(IntegrationTestCase):
	def setUp(self):
		self.pen, self.calf_feed = _calf_ration_item()
		if not self.calf_feed:
			self.skipTest("the calf pen has no ration on this site")
		self.milking = hm.post_calving_herd()
		if not self.milking:
			self.skipTest("no post-calving herd configured")
		_tidy(COW)
		_make_cow(COW, herd=self.milking)
		frappe.db.commit()
		self.addCleanup(_tidy, COW)
		self.gestation = int(hm.settings().get("gestation_period_days") or 0) or 280

	def _carrying(self, calving_in_days):
		"""A confirmed pregnancy that calves inside the window."""
		return _confirmed_service(COW, add_days(today(), -(self.gestation - calving_in_days)))

	def _calf_pen_draw_at_horizon(self, days):
		row = _draw_for(feed_forecast({"days": days}), self.calf_feed)
		return row["per_day_at_horizon"] if row else 0.0

	def test_a_calf_due_inside_the_window_raises_the_calf_pens_draw(self):
		"""The new mouth the flat projection never counted."""
		before = self._calf_pen_draw_at_horizon(60)
		self._carrying(20)
		after = self._calf_pen_draw_at_horizon(60)
		self.assertGreater(after, before, "a calving inside the window fed nobody extra")

	def test_the_calving_and_the_birth_are_both_scheduled(self):
		self._carrying(20)
		kinds = {w["kind"] for e in feed_forecast({"days": 60})["events"] for w in e["what"]}
		self.assertIn("birth", kinds)

	def test_she_leaves_the_milking_herd_before_she_calves(self):
		"""Drying off is a move the farm's own settings already describe, and it
		takes her draw out of the milking herd weeks before the calf arrives.

		She has to be far enough out for the dry-off to still be ahead of her: a
		cow calving in twenty days is already forty days past it on this farm's
		sixty-day rule, and a forecast cannot move an animal backwards. One
		standing in the milking herd past her own dry-off date is OVERDUE, which
		is the movement screen's business and not this one's.
		"""
		lead = hm.steamer_days_for(self.milking)
		self._carrying(lead + 30)
		moves = [
			w for e in feed_forecast({"days": lead + 60})["events"] for w in e["what"]
			if w["kind"] == "move" and w["from_herd"] == self.milking
		]
		self.assertTrue(moves, "a cow with her dry-off still ahead never leaves the milking herd")

	def test_an_abortion_takes_the_calf_back_out_of_the_forecast(self):
		"""THE CASE THIS WAS BUILT FOR. Nothing is edited — the pregnancy simply
		stops being one the farm is carrying, and the arithmetic follows."""
		self._carrying(20)
		with_calf = self._calf_pen_draw_at_horizon(60)

		loss = frappe.new_doc("Livestock Event")
		loss.event_type = "Abortion"
		loss.animal = COW
		loss.event_date = today()
		loss.operator = _employee()
		loss.flags.ignore_validate = True
		loss.insert(ignore_permissions=True)
		loss.db_set("docstatus", 1, update_modified=False)
		frappe.db.commit()

		after_loss = self._calf_pen_draw_at_horizon(60)
		self.assertLess(after_loss, with_calf,
		                "the calf pen is still being fed for a calf that was lost")

	def test_a_service_nobody_has_answered_yet_moves_nothing(self):
		"""A pending service might not have taken. Feeding for a calf that may
		never arrive is the mistake in the other direction."""
		before = self._calf_pen_draw_at_horizon(60)
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Service"
		doc.animal = COW
		doc.event_date = add_days(today(), -(self.gestation - 20))
		doc.service_date = doc.event_date
		doc.operator = _employee()
		doc.pregnancy_confirmation_status = "Pending"
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		doc.db_set("docstatus", 1, update_modified=False)
		frappe.db.commit()
		self.assertEqual(self._calf_pen_draw_at_horizon(60), before)
