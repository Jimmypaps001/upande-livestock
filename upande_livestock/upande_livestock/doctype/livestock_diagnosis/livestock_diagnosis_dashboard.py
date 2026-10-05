# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The check-up's Connections tab: the issue it posted, the case it was
escalated into, and its place on the animal's timeline."""

from frappe import _


def get_data():
	return {
		"fieldname": "reference_name",
		"dynamic_links": {"reference_name": ["Livestock Diagnosis", "reference_doctype"]},
		"internal_links": {"Stock Entry": "stock_entry", "Livestock Health Case": "related_case"},
		"transactions": [
			{"label": _("Stock"), "items": ["Stock Entry"]},
			{"label": _("Health"), "items": ["Livestock Health Case"]},
			{"label": _("Timeline"), "items": ["Livestock Event"]},
		],
	}
