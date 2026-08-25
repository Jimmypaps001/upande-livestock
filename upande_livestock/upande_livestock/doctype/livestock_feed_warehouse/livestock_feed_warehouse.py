# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockFeedWarehouse(Document):
	"""One candidate source warehouse for feed inputs.

	Row order (``idx``) is the search order: ``api.feeding._pick_source`` walks
	the list top-down and takes the first warehouse that can cover a line in
	full. Rows are configured on Livestock Settings.
	"""

	pass
