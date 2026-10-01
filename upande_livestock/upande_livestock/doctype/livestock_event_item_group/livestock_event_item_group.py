# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockEventItemGroup(Document):
	"""One item group an event type may consume.

	A row, not a setting: an event type has as many as the farm needs, and the
	two-kind `stock_items` it replaces could express exactly one each for drugs
	and semen.
	"""

	pass
