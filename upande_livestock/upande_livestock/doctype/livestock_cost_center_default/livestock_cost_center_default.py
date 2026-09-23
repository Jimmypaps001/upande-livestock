# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockCostCenterDefault(Document):
	"""The cost centre livestock movements take when the herd names none.

	One row per company, because this site runs a dairy and a flower business
	under the same roof: charging both to one centre is what the flat setting
	this replaced did. Read by
	``serverscripts.common.cost_center.setting_cost_center``.
	"""

	pass
