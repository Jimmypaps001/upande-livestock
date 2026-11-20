# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Loss scenarios: an injured, sick, dead or stolen animal and its insurance claim.

A Livestock Loss Scenario says what a kind of loss means for the farm: whether
to claim, on which Upande Asset incident type, what papers the insurer wants,
and what happens to the animal (sold for slaughter, sold live, written off).
A Livestock Loss is one animal's loss under a scenario, and carries the trail.

Nothing of the claim is reimplemented. The claim is Upande Asset's own
Insurance Claim, created as a Draft and moved on by Accounts in Upande Asset.
The animal leaves through the existing Livestock Disposal (sale draft invoice,
or scrap for a write-off).

THE SALE WAITS FOR THE CLAIM. Livestock Settings "Sale of an insured animal
waits for" says how far the claim must have got before a Sold disposal may be
submitted: Nothing, Claim recorded (anything past Draft) or Insurer approved.
The check is `sale_gate_message`, called from LivestockDisposal.before_submit,
so it binds the desk, the phone and the API alike. A Rejected or Cancelled
claim never blocks: the insurer has said no and the farm may sell.
"""

import json

import frappe
from frappe import _
from frappe.utils import escape_html, flt, get_url_to_form, getdate, today

from upande_livestock.serverscripts.common.envelope import as_dict

from upande_livestock.serverscripts.disposal.notify_accounts import parse_roles, recipients

NOTHING = "Nothing"
RECORDED = "Claim recorded"
APPROVED = "Insurer approved"
DEFAULT_GATE = RECORDED

# Claim statuses that satisfy each requirement.
PAST_DRAFT = ("Recorded", "Under Assessment", "Approved", "Partly Settled", "Settled", "Closed")
APPROVED_OR_BEYOND = ("Approved", "Partly Settled", "Settled", "Closed")
DEAD_ENDS = ("Rejected", "Cancelled")

OUTCOME_SLAUGHTER = "Sell for slaughter"
OUTCOME_LIVE = "Sell live"
OUTCOME_WRITE_OFF = "Write off"
SALES = (OUTCOME_SLAUGHTER, OUTCOME_LIVE)

# What the disposal is called when the animal is written off, by trigger.
WRITE_OFF_TYPE = {
	"Death": "Died — Natural Causes",
	"Disease": "Died — Disease",
	"Injury": "Died — Accident",
	"Theft": "Stolen",
}

ACCOUNTS_ROLES = ("Accounts Manager", "System Manager")
ACCOUNTS_FIELDS = ("sale_waits_for", "sale_invoice_alert_roles")


# --- settings -------------------------------------------------------------


def required_status():
	value = frappe.db.get_single_value("Livestock Settings", "sale_waits_for")
	return value if value in (NOTHING, RECORDED, APPROVED) else DEFAULT_GATE


def assert_may_change_accounts(fieldnames):
	"""Only Accounts Manager or System Manager may change the accounts fields."""
	if not set(fieldnames) & set(ACCOUNTS_FIELDS):
		return
	if frappe.session.user == "Administrator" or set(frappe.get_roles()) & set(ACCOUNTS_ROLES):
		return
	frappe.throw(
		_("Only an Accounts Manager or System Manager may change {0}.").format(
			", ".join(frappe.get_meta("Livestock Settings").get_label(f) for f in ACCOUNTS_FIELDS if f in fieldnames)
		),
		frappe.PermissionError,
	)


def claim_meets(status, requirement=None):
	requirement = requirement or required_status()
	if requirement == NOTHING:
		return True
	if status in DEAD_ENDS:
		return True
	if requirement == APPROVED:
		return status in APPROVED_OR_BEYOND
	return status in PAST_DRAFT


# --- reading the trail ----------------------------------------------------


def open_loss(animal):
	"""The animal's loss that is not closed yet (newest), or None."""
	rows = frappe.get_all("Livestock Loss", filters={"animal": animal, "status": ["!=", "Closed"]},
	                      pluck="name", order_by="creation desc", limit=1)
	return rows[0] if rows else None


def latest_loss(animal):
	rows = frappe.get_all("Livestock Loss", filters={"animal": animal}, pluck="name",
	                      order_by="creation desc", limit=1)
	return rows[0] if rows else None


def claim_state(claim):
	if not claim or not frappe.db.exists("Insurance Claim", claim):
		return None
	return frappe.db.get_value("Insurance Claim", claim, "status")


def sale_gate_message(animal):
	"""Why this animal may not be sold yet, or None when she may.

	Only an animal whose recorded loss raised an insurance claim is held; a sale
	with no loss behind it, or a loss with no claim, is never blocked.
	"""
	requirement = required_status()
	if requirement == NOTHING:
		return None
	loss = open_loss(animal)
	claim = loss and frappe.db.get_value("Livestock Loss", loss, "claim")
	if not claim:
		return None
	status = claim_state(claim)
	if status is None or claim_meets(status, requirement):
		return None
	return _("{0} cannot be sold yet: insurance claim {1} is {2}, and the sale waits for it to be {3}. "
	         "Accounts moves the claim on in Upande Asset.").format(
		animal, claim, status, _("recorded") if requirement == RECORDED else _("approved by the insurer"))


# --- scenarios ------------------------------------------------------------


def validate_scenario(doc):
	if doc.claim_insurance:
		if not doc.incident_type:
			frappe.throw(_("Choose the incident type the claim is raised under."))
		if not doc.loss_treatment:
			frappe.throw(_("Choose the loss treatment of the claim."))
		if doc.loss_treatment == "Total Loss" and doc.outcome in SALES:
			frappe.throw(_("A Total Loss claim needs the asset scrapped, which a sale does not do. "
			               "Use Impairment for a salvage sale, or Write off as the outcome."))
	else:
		doc.incident_type = None
		doc.loss_treatment = None
	seen = set()
	for row in doc.get("required_documents") or []:
		key = (row.document_name or "").strip().lower()
		if key in seen:
			frappe.throw(_("{0} is listed twice in the required documents.").format(row.document_name))
		seen.add(key)


def scenario_dict(name):
	doc = frappe.get_doc("Livestock Loss Scenario", name)
	return {
		"name": doc.name, "scenario_name": doc.scenario_name, "active": int(doc.active or 0),
		"trigger": doc.trigger, "outcome": doc.outcome, "description": doc.description,
		"claim_insurance": int(doc.claim_insurance or 0), "incident_type": doc.incident_type,
		"loss_treatment": doc.loss_treatment, "notify_roles": doc.notify_roles,
		"required_documents": [{"document_name": r.document_name, "mandatory": int(r.mandatory or 0)}
		                       for r in doc.required_documents],
	}


SEEDS = [
	{"scenario_name": "Injury - salvage slaughter", "trigger": "Injury", "claim_insurance": 1,
	 "incident_type": "Injury", "loss_treatment": "Impairment", "outcome": OUTCOME_SLAUGHTER,
	 "description": "Badly injured, sold for slaughter. Claimed as an Impairment (the carcass sale is the salvage, the claim covers the shortfall); the sale waits for the claim.",
	 "required_documents": [("Vet report", 1), ("Photos of the injury", 0)]},
	{"scenario_name": "Sudden death", "trigger": "Death", "claim_insurance": 1,
	 "incident_type": "Death / Mortality", "loss_treatment": "Total Loss", "outcome": OUTCOME_WRITE_OFF,
	 "description": "Found dead. Written off, claim for the loss.",
	 "required_documents": [("Vet post-mortem report", 1), ("Photo of ear tag", 1)]},
	{"scenario_name": "Theft", "trigger": "Theft", "claim_insurance": 1,
	 "incident_type": "Theft", "loss_treatment": "Total Loss", "outcome": OUTCOME_WRITE_OFF,
	 "description": "Stolen. Written off, claim for the loss.",
	 "required_documents": [("Police abstract", 1)]},
	{"scenario_name": "Low production cull", "trigger": "Low production", "claim_insurance": 0,
	 "outcome": OUTCOME_LIVE, "description": "Sold live for low production. No claim.",
	 "required_documents": []},
]


def ensure_loss_scenarios():
	"""Seed the four example scenarios on a site that has none. Idempotent, and
	a farm that deleted them does not get them back once it has any of its own."""
	if not frappe.db.table_exists("Livestock Loss Scenario"):
		return
	if frappe.db.count("Livestock Loss Scenario"):
		return
	for seed in SEEDS:
		doc = frappe.new_doc("Livestock Loss Scenario")
		doc.update({k: v for k, v in seed.items() if k != "required_documents"})
		doc.active = 1
		if doc.incident_type and not frappe.db.exists("Insurance Incident Type", doc.incident_type):
			# Upande Asset not seeded here (or renamed): the farm picks one.
			doc.incident_type = None
			doc.claim_insurance = 0
			doc.loss_treatment = None
		for name, mandatory in seed["required_documents"]:
			doc.append("required_documents", {"document_name": name, "mandatory": mandatory})
		doc.insert(ignore_permissions=True)


# --- the claim ------------------------------------------------------------


def create_claim(loss, scenario, documents=None):
	"""Draft the Upande Asset Insurance Claim for a loss. Returns (claim, note).

	`note` says why there is no claim (no cover, no asset, Upande Asset
	missing); a refusal from the claim itself is passed on in the same words.
	"""
	from upande_livestock.serverscripts.common import asset_cover

	if not asset_cover.available():
		return None, _("Upande Asset's insurance is not installed on this site, so no claim was raised.")
	asset = frappe.db.get_value("Animal", loss.animal, "asset_link")
	if not asset:
		return None, _("{0} is not on the fixed-asset register, so no claim was raised.").format(loss.animal)
	company = frappe.db.get_value("Asset", asset, "company")
	claim = frappe.new_doc("Insurance Claim")
	claim.update({
		"company": company,
		"asset": asset,
		"incident_date": loss.incident_date,
		"reported_date": today(),
		"incident_type": scenario.incident_type,
		"loss_treatment": scenario.loss_treatment,
		"description": "<p>{0}</p>".format(escape_html(loss.notes or "")) if loss.notes else "",
		"status": "Draft",
	})
	provided = {(d.get("document_name") or "").strip().lower(): d for d in (documents or [])}
	used = set()
	for req in scenario.required_documents:
		key = (req.document_name or "").strip().lower()
		given = provided.get(key) or {}
		used.add(key)
		claim.append("documents", {"document_name": req.document_name, "mandatory": req.mandatory,
		                           "attachment": given.get("attachment"), "remarks": given.get("remarks")})
	for key, given in provided.items():
		if key not in used and given.get("document_name"):
			claim.append("documents", {"document_name": given["document_name"], "mandatory": 0,
			                           "attachment": given.get("attachment"), "remarks": given.get("remarks")})
	frappe.db.savepoint("loss_claim")
	try:
		claim.flags.ignore_permissions = True
		claim.insert()
	except Exception as e:
		frappe.db.rollback(save_point="loss_claim")
		if isinstance(e, frappe.ValidationError):
			return None, str(getattr(e, "message", None) or e)
		raise
	attach_to_claim(claim)
	return claim, None


def check_private(documents):
	"""Claim papers (a police abstract, a vet report) are never public files."""
	for d in documents or []:
		url = d.get("attachment")
		if not url:
			continue
		private = frappe.db.get_value("File", {"file_url": url}, "is_private")
		if not private:
			frappe.throw(_("{0}: attach claim papers as private files.").format(d.get("document_name") or url))


def attach_to_claim(claim):
	"""Point each private file on the claim's documents at the claim it belongs to."""
	for row in claim.documents:
		if row.attachment:
			for name in frappe.get_all("File", filters={"file_url": row.attachment, "is_private": 1},
			                           or_filters=[["attached_to_doctype", "is", "not set"]], pluck="name"):
				frappe.db.set_value("File", name, {"attached_to_doctype": "Insurance Claim",
				                                   "attached_to_name": claim.name}, update_modified=False)


def missing_documents(claim_name):
	if not claim_name:
		return []
	return [r.document_name for r in frappe.get_all(
		"Insurance Claim Document", filters={"parent": claim_name, "parenttype": "Insurance Claim",
		                                     "mandatory": 1}, fields=["document_name", "attachment"])
		if not r.attachment]


# --- the animal leaves ----------------------------------------------------


def disposal_type_for(scenario):
	if scenario.outcome in SALES:
		return "Sold"
	return WRITE_OFF_TYPE.get(scenario.trigger, "Culled (Farm Use)")


def start_disposal(loss, scenario, sale=None):
	"""Create the Livestock Disposal for a loss: submitted for a write-off, a
	draft for a sale (it is submitted once the claim allows and a buyer is set)."""
	sale = sale or {}
	disposal = frappe.new_doc("Livestock Disposal")
	disposal.animal = loss.animal
	disposal.disposal_type = disposal_type_for(scenario)
	disposal.reason_details = "{0}: {1}{2}".format(
		scenario.scenario_name, loss.name, (" - " + loss.notes) if loss.notes else "")
	if scenario.outcome in SALES:
		disposal.disposal_date = today()
		disposal.customer = sale.get("customer") or None
		disposal.sale_price = sale.get("sale_price") or None
		disposal.buyer_name = sale.get("buyer_name")
	else:
		disposal.disposal_date = min(getdate(loss.incident_date), getdate(today()))
	disposal.flags.ignore_permissions = True
	disposal.insert()
	frappe.db.set_value("Livestock Loss", loss.name, {"disposal": disposal.name, "disposal_status": "Draft"},
	                    update_modified=False)
	return disposal


def advance(loss_name, sale=None):
	"""Take the loss as far as it can go now. Returns the loss's status.

	Write off: submit the disposal (scrap). Sale: submit it when the claim lets
	the animal go and a buyer and price are set; otherwise it waits as a draft.
	"""
	loss = frappe.get_doc("Livestock Loss", loss_name)
	scenario = frappe.get_doc("Livestock Loss Scenario", loss.scenario)
	if loss.status == "Closed":
		return "Closed"
	if loss.disposal and frappe.db.get_value("Livestock Disposal", loss.disposal, "docstatus") == 2:
		loss.db_set("disposal", None, update_modified=False)
		loss.disposal = None
	disposal = frappe.get_doc("Livestock Disposal", loss.disposal) if loss.disposal else start_disposal(loss, scenario, sale)
	if disposal.docstatus == 1:
		return _set_status(loss, "Closed")
	if scenario.outcome in SALES:
		sale = sale or {}
		blocked = sale_gate_message(loss.animal)
		if sale.get("customer") or sale.get("sale_price") or sale.get("buyer_name"):
			disposal.customer = sale.get("customer") or disposal.customer
			disposal.sale_price = sale.get("sale_price") or disposal.sale_price
			disposal.buyer_name = sale.get("buyer_name") or disposal.buyer_name
			disposal.flags.ignore_permissions = True
			disposal.save()
		if blocked:
			return _set_status(loss, "Awaiting claim")
		if not (disposal.customer and disposal.sale_price):
			return _set_status(loss, "Sale waiting")
	disposal.flags.ignore_permissions = True
	disposal.submit()
	return _set_status(loss, "Closed")


def _set_status(loss, status):
	frappe.db.set_value("Livestock Loss", loss.name, "status", status, update_modified=False)
	return status


# --- keeping the loss in step ---------------------------------------------


def on_disposal_submit(doc):
	loss = frappe.db.get_value("Livestock Loss", {"disposal": doc.name}, "name")
	if not loss:
		return
	frappe.db.set_value("Livestock Loss", loss, {
		"status": "Closed", "disposal_status": "Submitted", "sales_invoice": doc.get("sales_invoice")},
		update_modified=False)
	notify_step(loss, _("Animal left the herd"),
	            _("{0} was disposed of ({1}).").format(doc.animal, doc.disposal_type))


def on_disposal_cancel(doc):
	loss = frappe.db.get_value("Livestock Loss", {"disposal": doc.name}, "name")
	if loss:
		frappe.db.set_value("Livestock Loss", loss, {
			"status": "Recorded", "disposal": None, "disposal_status": None, "sales_invoice": None},
			update_modified=False)


def claim_changed(doc, method=None):
	"""Insurance Claim doc event: mirror its status onto the loss, tell people,
	and wake a sale that was waiting on it."""
	loss = frappe.db.get_value("Livestock Loss", {"claim": doc.name}, ["name", "claim_status", "status", "animal"], as_dict=True)
	if not loss:
		return
	status = "Cancelled" if method == "on_cancel" else doc.status
	if status == loss.claim_status:
		return
	updates = {"claim_status": status}
	if loss.status == "Awaiting claim" and claim_meets(status):
		updates["status"] = "Sale waiting"
	frappe.db.set_value("Livestock Loss", loss.name, updates, update_modified=False)
	notify_step(loss.name, _("Insurance claim {0}").format(status),
	            _("Claim {0} for {1} is now {2}.").format(doc.name, loss.animal, status))
	if updates.get("status") == "Sale waiting":
		notify_step(loss.name, _("Sale can go ahead"),
		            _("The claim for {0} is {1}, so her sale is released.").format(loss.animal, status))


# --- notices --------------------------------------------------------------


def notify_step(loss_name, subject, detail):
	"""Queue a notice for the roles of the loss's scenario. Never blocks or raises."""
	try:
		frappe.enqueue("upande_livestock.serverscripts.common.loss.send_notice", queue="short",
		               enqueue_after_commit=True, loss=loss_name, subject=subject, detail=detail)
	except Exception:
		frappe.log_error(title="livestock loss notice not queued")


def send_notice(loss, subject, detail):
	try:
		scenario = frappe.db.get_value("Livestock Loss", loss, "scenario")
		roles = parse_roles(frappe.db.get_value("Livestock Loss Scenario", scenario, "notify_roles")) if scenario else []
		users = [u for u in recipients(roles or None) if u not in ("Administrator", "Guest")]
		if not users:
			return []
		link = get_url_to_form("Livestock Loss", loss)
		body = "<p>{0}</p><p><a href=\"{1}\">{2}</a></p>".format(escape_html(detail), link, escape_html(loss))
		full = "{0}: {1}".format(loss, subject)
		frappe.sendmail(recipients=users, subject=full, message=body,
		                reference_doctype="Livestock Loss", reference_name=loss)
		from upande_livestock.serverscripts.common.notifications import notify

		notify(users, full, body, "Livestock Loss", loss)
		return users
	except Exception:
		frappe.log_error(title="livestock loss notice failed")
		return []


# --- shared by the endpoints (serverscripts/losses) -----------------------


def merge(payload, **kw):
	d = dict(as_dict(payload) or {}) if payload else {}
	d.update({k: v for k, v in kw.items() if v is not None})
	return d


def documents(raw):
	if isinstance(raw, str):
		raw = json.loads(raw or "[]")
	return [dict(r) for r in (raw or []) if isinstance(r, dict)]


def sale(d):
	return {"customer": d.get("customer"), "sale_price": flt(d.get("sale_price")) or None,
	        "buyer_name": d.get("buyer_name")}


def trail(name):
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
		claim["missing_documents"] = missing_documents(doc.claim)
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
		"disposal": disposal, "waiting_for": (sale_gate_message(doc.animal) if doc.status != "Closed" else None),
		"requirement": required_status(),
	}
