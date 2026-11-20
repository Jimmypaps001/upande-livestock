# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockLossScenario(Document):
	def validate(self):
		from upande_livestock.serverscripts.common.loss import validate_scenario

		validate_scenario(self)
