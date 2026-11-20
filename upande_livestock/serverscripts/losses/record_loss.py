# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Record an animal's loss under a scenario (claim through Upande Asset, then the animal leaves as far as the rules allow)."""

import frappe
from frappe import _
from frappe.utils import getdate, today

from upande_livestock.serverscripts.common import loss
from upande_livestock.serverscripts.common.envelope import guard, run


@frappe.whitelist()
def record_loss(payload=None, animal=None, scenario=None, incident_date=None, notes=None,
                documents=None, customer=None, sale_price=None, buyer_name=None):
	"""Record an animal's loss under a scenario.

	Raises the Insurance Claim (Draft, through Upande Asset) when the scenario
	claims and the animal has cover, then takes the animal out as far as the
	rules allow: a write-off is posted at once, a sale waits as a draft until the
	claim reaches the stage Livestock Settings asks for.
	"""

	def go():
		guard("Livestock Loss")
		d = loss.merge(payload, animal=animal, scenario=scenario, incident_date=incident_date, notes=notes,
		           documents=documents, customer=customer, sale_price=sale_price, buyer_name=buyer_name)
		name = (d.get("animal") or "").strip()
		if not name or not frappe.db.exists("Animal", name):
			frappe.throw(_("Select an animal."))
		status, disabled = frappe.db.get_value("Animal", name, ["status", "disabled"])
		if disabled or status in ("Dead", "Sold", "Culled", "Transferred Out"):
			frappe.throw(_("{0} has already left the herd.").format(name))
		if not d.get("scenario") or not frappe.db.exists("Livestock Loss Scenario", d["scenario"]):
			frappe.throw(_("Choose the loss scenario."))
		sc = frappe.get_doc("Livestock Loss Scenario", d["scenario"])
		if not sc.active:
			frappe.throw(_("Scenario {0} is switched off.").format(sc.name))
		if loss.open_loss(name):
			frappe.throw(_("{0} already has a loss in progress ({1}).").format(name, loss.open_loss(name)))
		when = getdate(d.get("incident_date") or today())
		if when > getdate(today()):
			frappe.throw(_("The incident date cannot be in the future."))

		loss.check_private(loss.documents(d.get("documents")))

		doc = frappe.new_doc("Livestock Loss")
		doc.update({"animal": name, "scenario": sc.name, "incident_date": when, "notes": d.get("notes"),
		            "status": "Recorded"})
		doc.flags.ignore_permissions = True
		doc.insert()
		claim_note = None
		if sc.claim_insurance:
			claim, claim_note = loss.create_claim(doc, sc, loss.documents(d.get("documents")))
			if claim:
				doc.db_set({"claim": claim.name, "claim_status": claim.status,
				            "missing_documents": ", ".join(loss.missing_documents(claim.name))},
				           update_modified=False)
			else:
				doc.db_set("claim_note", claim_note, update_modified=False)
		loss.notify_step(doc.name, _("Loss recorded"), _("{0}: {1} ({2}).").format(name, sc.scenario_name, when))

		# The animal leaves through a disposal, which is its own permission.
		disposal_note = None
		if frappe.has_permission("Livestock Disposal", "create"):
			result = loss.advance(doc.name, loss.sale(d))
		else:
			result = "Recorded"
			disposal_note = _("A manager completes the disposal of {0}.").format(name)
		doc.reload()
		return {"ok": True, "name": doc.name, "status": result, "claim": doc.claim,
		        "claim_status": doc.claim_status, "claim_note": claim_note,
		        "missing_documents": doc.missing_documents, "disposal": doc.disposal,
		        "disposal_note": disposal_note, "blocked": loss.sale_gate_message(name)}

	return run(go, "livestock record_loss failed")
