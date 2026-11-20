# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Endpoints of the loss flow: record a loss, follow its trail, edit scenarios.

The phone calls `record_loss` and `complete_loss`; the rules (claim through
Upande Asset, the sale waiting for the claim) live in common/loss.py and the
Livestock Disposal controller, not here.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from upande_livestock.serverscripts.common import asset_cover, loss
from upande_livestock.serverscripts.common.envelope import as_dict, guard, guard_read, run


def _merge(payload, **kw):
	d = dict(as_dict(payload) or {}) if payload else {}
	d.update({k: v for k, v in kw.items() if v is not None})
	return d


def _documents(raw):
	if isinstance(raw, str):
		raw = json.loads(raw or "[]")
	return [dict(r) for r in (raw or []) if isinstance(r, dict)]


def _sale(d):
	return {"customer": d.get("customer"), "sale_price": flt(d.get("sale_price")) or None,
	        "buyer_name": d.get("buyer_name")}


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
		d = _merge(payload, animal=animal, scenario=scenario, incident_date=incident_date, notes=notes,
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

		doc = frappe.new_doc("Livestock Loss")
		doc.update({"animal": name, "scenario": sc.name, "incident_date": when, "notes": d.get("notes"),
		            "status": "Recorded"})
		doc.flags.ignore_permissions = True
		doc.insert()
		claim_note = None
		if sc.claim_insurance:
			claim, claim_note = loss.create_claim(doc, sc, _documents(d.get("documents")))
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
			result = loss.advance(doc.name, _sale(d))
		else:
			result = "Recorded"
			disposal_note = _("A manager completes the disposal of {0}.").format(name)
		doc.reload()
		return {"ok": True, "name": doc.name, "status": result, "claim": doc.claim,
		        "claim_status": doc.claim_status, "claim_note": claim_note,
		        "missing_documents": doc.missing_documents, "disposal": doc.disposal,
		        "disposal_note": disposal_note, "blocked": loss.sale_gate_message(name)}

	return run(go, "livestock record_loss failed")


@frappe.whitelist()
def complete_loss(payload=None, loss_name=None, customer=None, sale_price=None, buyer_name=None):
	"""Finish a loss that is waiting: post the write-off, or release the sale
	(buyer and price) now that the claim lets it go. Refuses, with the reason,
	while the claim has not got far enough."""

	def go():
		guard("Livestock Disposal")
		d = _merge(payload, loss_name=loss_name, customer=customer, sale_price=sale_price,
		           buyer_name=buyer_name)
		name = d.get("loss_name") or d.get("loss")
		if not name or not frappe.db.exists("Livestock Loss", name):
			frappe.throw(_("Choose the loss."))
		animal = frappe.db.get_value("Livestock Loss", name, "animal")
		message = loss.sale_gate_message(animal)
		result = loss.advance(name, _sale(d))
		if result == "Awaiting claim":
			frappe.throw(message or _("The sale is waiting for the insurance claim."))
		if result == "Sale waiting":
			frappe.throw(_("Choose the Customer and the sale price to complete the sale."))
		return {"ok": True, "name": name, "status": result}

	return run(go, "livestock complete_loss failed")


def _trail(name):
	doc = frappe.get_doc("Livestock Loss", name)
	sc = frappe.db.get_value("Livestock Loss Scenario", doc.scenario, ["trigger", "outcome"], as_dict=True) or {}
	claim = None
	if doc.claim and frappe.db.exists("Insurance Claim", doc.claim):
		c = frappe.db.get_value(
			"Insurance Claim", doc.claim,
			["name", "status", "docstatus", "amount_claimed", "amount_approved", "amount_received",
			 "outstanding_amount", "shortfall_amount", "insurer", "policy_number", "claim_journal_entry"],
			as_dict=True)
		claim = dict(c)
		claim["missing_documents"] = loss.missing_documents(doc.claim)
		if c.status != doc.claim_status:
			frappe.db.set_value("Livestock Loss", name, "claim_status", c.status, update_modified=False)
	disposal = None
	if doc.disposal and frappe.db.exists("Livestock Disposal", doc.disposal):
		disposal = dict(frappe.db.get_value(
			"Livestock Disposal", doc.disposal,
			["name", "docstatus", "disposal_type", "disposal_date", "sale_price", "customer", "sales_invoice"],
			as_dict=True))
		if disposal.get("sales_invoice"):
			disposal["invoice_status"] = frappe.db.get_value("Sales Invoice", disposal["sales_invoice"], "docstatus")
	return {
		"name": doc.name, "animal": doc.animal, "animal_name": doc.animal_name, "scenario": doc.scenario,
		"trigger": sc.get("trigger"), "outcome": sc.get("outcome"), "incident_date": str(doc.incident_date),
		"notes": doc.notes, "status": doc.status, "claim": claim, "claim_note": doc.claim_note,
		"disposal": disposal, "waiting_for": (loss.sale_gate_message(doc.animal) if doc.status != "Closed" else None),
		"requirement": loss.required_status(),
	}


@frappe.whitelist()
def loss_trail(payload=None, animal=None):
	"""Every loss of one animal, newest first, each with its claim and disposal."""

	def go():
		guard_read("Livestock Loss")
		d = _merge(payload, animal=animal)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		names = frappe.get_all("Livestock Loss", filters={"animal": d["animal"]}, pluck="name",
		                       order_by="creation desc")
		return {"ok": True, "losses": [_trail(n) for n in names], "requirement": loss.required_status(),
		        "cover": asset_cover.cover_for_animal(d["animal"])["state"]}

	return run(go, "livestock loss_trail failed")


@frappe.whitelist()
def loss_claims(payload=None, status=None):
	"""For Accounts: every loss that raised a claim, with where the claim stands."""

	def go():
		guard_read("Livestock Loss")
		d = _merge(payload, status=status)
		rows = frappe.get_all(
			"Livestock Loss", filters={"claim": ["is", "set"]},
			fields=["name", "animal", "animal_name", "scenario", "incident_date", "claim", "claim_status",
			        "status", "disposal", "sales_invoice", "missing_documents"],
			order_by="incident_date desc, creation desc", limit=500)
		live = {c.name: c for c in frappe.get_all(
			"Insurance Claim", filters={"name": ["in", [r.claim for r in rows]]} if rows else {"name": ""},
			fields=["name", "status", "amount_claimed", "amount_approved", "amount_received",
			        "outstanding_amount"])}
		out = []
		for r in rows:
			c = live.get(r.claim)
			item = dict(r, incident_date=str(r.incident_date))
			if c:
				item.update({"claim_status": c.status, "amount_claimed": c.amount_claimed,
				             "amount_approved": c.amount_approved, "amount_received": c.amount_received,
				             "outstanding_amount": c.outstanding_amount})
			if d.get("status") and item.get("claim_status") != d["status"]:
				continue
			out.append(item)
		return {"ok": True, "claims": out, "requirement": loss.required_status()}

	return run(go, "livestock loss_claims failed")


@frappe.whitelist()
def loss_scenarios(payload=None, include_inactive=None):
	"""The scenarios, for the picker (active only) or the editor (all)."""

	def go():
		guard_read("Livestock Loss Scenario")
		d = _merge(payload, include_inactive=include_inactive)
		filters = {} if int(d.get("include_inactive") or 0) else {"active": 1}
		names = frappe.get_all("Livestock Loss Scenario", filters=filters, pluck="name", order_by="scenario_name")
		return {"ok": True, "scenarios": [loss.scenario_dict(n) for n in names],
		        "requirement": loss.required_status(),
		        "incident_types": frappe.get_all("Insurance Incident Type", filters={"enabled": 1}, pluck="name",
		                                         order_by="name") if frappe.db.exists("DocType", "Insurance Incident Type") else []}

	return run(go, "livestock loss_scenarios failed")


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
