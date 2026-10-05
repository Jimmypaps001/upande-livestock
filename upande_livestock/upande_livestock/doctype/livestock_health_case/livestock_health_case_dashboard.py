# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The case's Connections tab: every issue its treatments posted, and its
place on the animal's timeline."""

from frappe import _


def get_data():
	return {
		"fieldname": "reference_name",
		"dynamic_links": {"reference_name": ["Livestock Health Case", "reference_doctype"]},
		"internal_links": {"Stock Entry": ["treatments", "stock_entry_ref"]},
		"transactions": [
			{"label": _("Stock"), "items": ["Stock Entry"]},
			{"label": _("Timeline"), "items": ["Livestock Event"]},
		],
	}
