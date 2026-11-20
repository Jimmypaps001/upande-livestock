# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Delete a scenario nothing has used; one in use is switched off."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


@frappe.whitelist()
def delete_loss_scenario(payload):
	"""Delete a scenario nothing has used; one in use is switched off instead."""

	def go():
		guard("Livestock Loss Scenario", employee=False)
		name = as_dict(payload).get("name")
		if not name or not frappe.db.exists("Livestock Loss Scenario", name):
			frappe.throw(_("Choose the scenario."))
		if frappe.db.exists("Livestock Loss", {"scenario": name}):
			frappe.db.set_value("Livestock Loss Scenario", name, "active", 0)
			return {"ok": True, "deleted": False, "message": _("Used by recorded losses, so it was switched off.")}
		frappe.delete_doc("Livestock Loss Scenario", name)
		return {"ok": True, "deleted": True}

	return run(go, "livestock delete_loss_scenario failed")
