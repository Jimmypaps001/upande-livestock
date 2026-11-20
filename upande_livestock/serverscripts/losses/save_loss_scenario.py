# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Create or change a scenario (managers only)."""

import frappe

from upande_livestock.serverscripts.common import loss
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


@frappe.whitelist()
def save_loss_scenario(payload):
	"""Create or change a scenario. Managers only (create permission on the doctype)."""

	def go():
		guard("Livestock Loss Scenario", employee=False)
		d = as_dict(payload)
		if d.get("name") and frappe.db.exists("Livestock Loss Scenario", d["name"]):
			doc = frappe.get_doc("Livestock Loss Scenario", d["name"])
		else:
			doc = frappe.new_doc("Livestock Loss Scenario")
		for f in ("scenario_name", "trigger", "outcome", "description", "incident_type", "loss_treatment",
		          "notify_roles"):
			if f in d and (doc.is_new() or f != "scenario_name"):
				doc.set(f, d.get(f) or None)
		for f in ("active", "claim_insurance"):
			if f in d:
				doc.set(f, 1 if int(d.get(f) or 0) else 0)
		if "required_documents" in d:
			doc.set("required_documents", [])
			for r in d.get("required_documents") or []:
				if (r.get("document_name") or "").strip():
					doc.append("required_documents", {"document_name": r["document_name"].strip(),
					                                  "mandatory": 1 if int(r.get("mandatory") or 0) else 0})
		doc.save()
		return {"ok": True, "scenario": loss.scenario_dict(doc.name)}

	return run(go, "livestock save_loss_scenario failed")
