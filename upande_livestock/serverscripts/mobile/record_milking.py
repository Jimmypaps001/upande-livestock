# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Record a milking from the handset.

A thin, frozen path over `milking.create_milk_recording`. It exists for the
same reason `record_animal_event` does: the phone should learn one path per
thing it records, and keep it across every backend reorganisation.

Milk is recorded in farm wall-clock time, not UTC. The app builds `milking_time`
from the device clock deliberately (see the clean branch's DateTimeField), so
this passes it through untouched rather than re-deriving it server-side from a
timestamp that has already crossed a timezone.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, run
from upande_livestock.serverscripts.milking.create_milk_recording import create_milk_recording


@frappe.whitelist()
def record_milking(payload=None):
	def go():
		# from_handset: a milker at the parlour cannot have a bulk tank SCC, so
		# the "quality required at milking" rule never blocks them. The recording
		# is saved and flagged as awaiting quality instead, and turns up on the
		# Quality page for whoever has the creamery docket.
		return create_milk_recording(as_dict(payload), from_handset=True)

	return run(go, "livestock mobile record_milking failed")
