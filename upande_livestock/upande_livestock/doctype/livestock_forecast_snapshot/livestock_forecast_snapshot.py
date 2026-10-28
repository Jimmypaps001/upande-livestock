# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockForecastSnapshot(Document):
	"""What the forecast said, on one day, for one week and one herd (or the farm).

	Written weekly by serverscripts.forecast.snapshot so the accuracy view can
	compare what was predicted with what was actually sold or slaughtered.
	"""
