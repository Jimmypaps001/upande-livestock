# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockBoughtInConcentrate(Document):
	"""A concentrate the farm buys ready-packed rather than mixing.

	Nothing in the item data separates one from silage or hay — every feed item
	sits in the DAIRY group with ``is_purchase_item = 1``, the mixed concentrates
	included. The only thing that marks a mixed concentrate is having a BOM, so a
	bought-in one has to be named here for the feeding programme to treat it as a
	concentrate rather than a plain raw material.
	"""

	pass
