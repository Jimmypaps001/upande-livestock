# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What an average cow on this farm looks like, to compare one against."""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.envelope import guard_read, run


def _median(values):
	rows = sorted(v for v in values if v is not None)
	if not rows:
		return None
	mid = len(rows) // 2
	return rows[mid] if len(rows) % 2 else (rows[mid - 1] + rows[mid]) / 2.0


@frappe.whitelist()
def herd_benchmarks():
	"""The farm's middle cow, per measure.

	MEDIAN, NOT MEAN. One nine-lactation matriarch or one heifer bought in at
	six years old drags a mean far enough that half the herd reads as "below
	average", which is exactly the comparison this exists to make honest. The
	median says what a normal cow here looks like.

	Each measure is taken over the animals that HAVE it rather than over the
	whole herd: a maiden heifer has no calving interval, and counting her as a
	zero would make every cow that has calved look above average.
	"""

	def go():
		guard_read("Animal")
		rows = frappe.get_all(
			"Animal",
			filters=[
				["status", "not in", list(RETIRED_STATUSES)],
				["disabled", "=", 0],
				["sex", "=", "Female"],
			],
			fields=["name", "parity", "conception_rate"],
			limit_page_length=0,
		)
		return {
			"ok": True,
			"cows": len(rows),
			"parity": _median([flt(r.parity) for r in rows if flt(r.parity) > 0]),
			"conception_rate": _median(
				[flt(r.conception_rate) for r in rows if flt(r.conception_rate) > 0]
			),
		}

	return run(go, "livestock herd_benchmarks failed")
