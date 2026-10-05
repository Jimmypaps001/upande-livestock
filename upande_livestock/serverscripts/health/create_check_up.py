"""Record a routine check-up as a Livestock Diagnosis."""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common.company import company_or_throw
from upande_livestock.serverscripts.common.employee import employee_or_throw
from upande_livestock.serverscripts.husbandry._shared import _clean_drug_rows
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common import event_items
from upande_livestock.serverscripts.common.health_case import open_case_for, open_file


#: The action that means "this is a case now". A value on the doctype since it
#: was written, and until now acted on nowhere.
ESCALATED = "Escalated to Case"



@frappe.whitelist()
def create_check_up(payload):
	"""Record a routine check-up as a Livestock Diagnosis.

	LivestockDiagnosis.on_submit() calls sync_event_for(self, "Check Up"), so the
	animal's timeline event is created by the doctype — not here.

	A CHECK-UP IS WHERE A FILE COMES FROM. `action_taken` has had "Escalated to
	Case" on it since the doctype was written and nothing ever acted on it: the
	check said escalate, and then a person had to remember to go and open a case
	by hand on another screen, which is the step that does not happen. An
	escalation opens the file here, unless she already has one open — in which
	case this morning belongs in the file she has, and opening a second would
	split one illness across two.

	"Treated on Spot" is not an escalation and does not open anything. It
	refuses instead: a check up that would issue a drug to an animal with no open
	file is stopped in the same words `treat_animal` uses, because treating a cow
	is issuing stock to her and that belongs in a file. The file is not opened
	here — nothing may open a second file for an illness already being treated.
	A check that issues nothing is untouched; looking at a cow is not treating
	her.
	"""

	def go():
		guard("Livestock Diagnosis")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("action_taken"):
			frappe.throw(_("Select the action taken."))
		doc = frappe.new_doc("Livestock Diagnosis")
		doc.animal = d.get("animal")
		doc.company = company_or_throw(d.get("company"))
		diagnosis_date, is_backdated = backdate.resolve(d, "diagnosis_date")
		backdate.assert_allowed(is_backdated)
		doc.diagnosis_date = diagnosis_date
		backdate.stamp(doc, is_backdated)
		doc.operator = employee_or_throw(d.get("operator"))
		doc.reason_for_check = d.get("reason_for_check")
		doc.appearance = d.get("appearance") or None
		doc.hydration = d.get("hydration") or None
		doc.temperature_c = flt(d.get("temperature_c")) or None
		doc.respiration_rate = int(flt(d.get("respiration_rate"))) or None
		doc.heart_rate = int(flt(d.get("heart_rate"))) or None
		doc.bcs = flt(d.get("bcs")) or None
		doc.lameness_score = int(flt(d.get("lameness_score"))) or None
		doc.suggested_disease = d.get("suggested_disease") or None
		doc.differential_notes = d.get("differential_notes")
		doc.action_taken = d.get("action_taken")
		doc.action_notes = d.get("action_notes")
		doc.follow_up_date = d.get("follow_up_date") or None
		# Anything given at the check. LivestockDiagnosis.post_drug_issue posts these
		# out of the drug store on submit, and blocks the check if it cannot.
		# Built once: the guard below and the rows share a definition of what
		# counts as issuing a drug, and two calls could only drift apart.
		drugs = _clean_drug_rows(
			d.get("drugs"), d.get("source_warehouse") or event_items.default_store("Check Up")
		)

		# Treating a cow is issuing stock to her, and that belongs in a file.
		# `treat_animal` has always refused this; a check up quietly did not, and
		# said so afterwards in a toast that fades — so the drugs went out and
		# the file was a suggestion. Same rule, same words.
		#
		# ESCALATING IS EXEMPT, because escalating IS saying what is wrong with
		# her: the branch below opens the file as part of the same action.
		# Without this a vet who escalated AND gave a drug was told to go and do
		# the thing they were already doing, and `run()` rolled the whole check
		# up back — so nothing was recorded at all.
		if drugs and d.get("action_taken") != ESCALATED and not open_case_for(d["animal"]):
			frappe.throw(
				_("{0} has no open file. Say what is wrong with her and a new one will be "
				  "opened for this treatment.").format(d["animal"])
			)

		for drug in drugs:
			doc.append("drug_issues", drug)
		doc.insert()
		doc.submit()
		doc.reload()

		standing = open_case_for(doc.animal)
		case, opened = None, False
		if doc.action_taken == ESCALATED:
			if standing:
				case = standing["name"]
			else:
				case = open_file({
					"animal": doc.animal,
					"company": doc.company,
					"opened_date": doc.diagnosis_date,
					"opened_by": doc.operator,
					"presenting_symptoms": doc.reason_for_check or doc.action_notes
					                       or _("Escalated from a check-up."),
					"provisional_diagnosis": doc.suggested_disease,
					"severity": d.get("severity"),
				}, opened_from=_("a check-up")).name
				opened = True
			# The check-up says which case it was escalated into. related_case was
			# never written, so the link only ran one way.
			doc.db_set("related_case", case, update_modified=False)

		return {
			"ok": True,
			"name": doc.name,
			"action_taken": doc.action_taken,
			"stock_entry": doc.stock_entry or "",
			"drugs_issued": len(doc.drug_issues or []),
			# The file this check-up belongs to, if it belongs to one.
			"case": case,
			"case_opened": opened,
			"open_case": standing["name"] if standing else None,
			# Whether the screen should ask about opening one. Asked, never
			# assumed: a dose at the crush may be a one-off, and only the person
			# who looked at her knows.
		}

	return run(go, "livestock create_check_up failed")
