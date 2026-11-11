# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockFeedHistoryItem(Document):
	"""One feed on a history day; the parent works out the amount, so it is never typed out of step."""

	pass
