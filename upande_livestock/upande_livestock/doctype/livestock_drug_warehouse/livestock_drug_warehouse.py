# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockDrugWarehouse(Document):
	"""One store the drug and semen pickers look in.

	The same shape as ``Livestock Feed Warehouse``, and for the same reason:
	the drugs a farm holds are spread across the stores it actually uses, not
	gathered in one. Row order is the search order — see
	``serverscripts.common.stock.drug_source_warehouses``.
	"""

	pass
