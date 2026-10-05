# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The event's Connections tab: the stock it moved.

The Stock Entry does not link back to the event, so these are read off the
event's own fields (internal links): the issue it posted (for a Health Case or
Check Up mirror, the issue its source posted), and for a Feeding the Work Order
its batch was mixed on, whose own Connections list the mixing entries.
"""

from frappe import _


def get_data():
	return {
		"fieldname": "related_service",
		"internal_links": {
			"Stock Entry": "stock_entry",
			"Work Order": "feed_work_order",
		},
		"transactions": [
			{"label": _("Stock"), "items": ["Stock Entry", "Work Order"]},
		],
	}
