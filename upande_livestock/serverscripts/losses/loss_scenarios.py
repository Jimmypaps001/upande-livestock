# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The loss scenarios, for the picker or the editor."""

import frappe

from upande_livestock.serverscripts.common import loss
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def loss_scenarios(payload=None, include_inactive=None):
	"""The scenarios, for the picker (active only) or the editor (all)."""

	def go():
		guard_read("Livestock Loss Scenario")
		d = loss.merge(payload, include_inactive=include_inactive)
		filters = {} if int(d.get("include_inactive") or 0) else {"active": 1}
		names = frappe.get_all("Livestock Loss Scenario", filters=filters, pluck="name", order_by="scenario_name")
		return {"ok": True, "scenarios": [loss.scenario_dict(n) for n in names],
		        "requirement": loss.required_status(),
		        "incident_types": frappe.get_all("Insurance Incident Type", filters={"enabled": 1}, pluck="name",
		                                         order_by="name") if frappe.db.exists("DocType", "Insurance Incident Type") else []}

	return run(go, "livestock loss_scenarios failed")
