# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The disposal's Connections tab: the sale invoice or write-off it posted,
and the insurance claim raised on it."""

from frappe import _


def get_data():
	return {
		"fieldname": "disposal",
		"internal_links": {"Sales Invoice": "sales_invoice", "Journal Entry": "writeoff_journal_entry"},
		"transactions": [
			{"label": _("Postings"), "items": ["Sales Invoice", "Journal Entry"]},
			{"label": _("Insurance"), "items": ["Livestock Insurance Claim"]},
		],
	}
