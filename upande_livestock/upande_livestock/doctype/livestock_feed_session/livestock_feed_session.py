# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockFeedSession(Document):
	"""One mixing of a herd's feed day (Full, or half 1 / half 2).

	Written by `serverscripts/feeding/_sessions.py`; the sessions that are not
	Cancelled add up to how much of the day the herd has been fed.
	"""
