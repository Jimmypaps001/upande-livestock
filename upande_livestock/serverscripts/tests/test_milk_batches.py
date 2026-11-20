# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The milk batches endpoint groups recordings by date and shift (the pure part; no site needed)."""

import unittest

from upande_livestock.serverscripts.quality.milk_batches import group_batches, shift_of


def _row(name, herd, date, time, kg):
	return {"name": name, "herd": herd, "recording_date": date, "milking_time": time, "net_yield_kg": kg}


class TestMilkBatches(unittest.TestCase):
	def test_shift_boundaries(self):
		self.assertEqual(shift_of("05:30:00"), "Morning")
		self.assertEqual(shift_of("11:59"), "Morning")
		self.assertEqual(shift_of("12:00:00"), "Afternoon")
		self.assertEqual(shift_of("16:59:00"), "Afternoon")
		self.assertEqual(shift_of("17:00"), "Evening")
		self.assertEqual(shift_of(None), "Morning")

	def test_groups_by_date_and_shift_newest_first(self):
		rows = [
			_row("R1", "A", "2026-11-18", "06:00:00", 100),
			_row("R2", "B", "2026-11-18", "07:00:00", 250.5),
			_row("R3", "A", "2026-11-18", "17:30:00", 90),
			_row("R4", "A", "2026-11-19", "06:00:00", 80),
		]
		out = group_batches(rows, tested={"R2"})
		self.assertEqual([b["key"] for b in out], ["2026-11-19|Morning", "2026-11-18|Evening", "2026-11-18|Morning"])
		m = out[2]
		self.assertEqual(m["total_kg"], 350.5)
		self.assertEqual(m["herds"], ["A", "B"])
		self.assertEqual(m["milk_recording"], "R2")
		self.assertTrue(m["tested"])
		self.assertFalse(out[0]["tested"])
