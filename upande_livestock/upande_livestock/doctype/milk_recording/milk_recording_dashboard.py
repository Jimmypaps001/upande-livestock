# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The milking's Connections tab: the receipt into stock and the revenue entry."""

from frappe import _


def get_data():
	return {
		"fieldname": "milk_recording",
		"internal_links": {"Stock Entry": "stock_entry", "Journal Entry": "journal_entry"},
		"transactions": [
			{"label": _("Postings"), "items": ["Stock Entry", "Journal Entry"]},
		],
	}
