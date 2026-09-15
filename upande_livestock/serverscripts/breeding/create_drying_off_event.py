"""Dry off a cow, ending her lactation."""

import frappe
from frappe import _

from upande_livestock.serverscripts.husbandry._shared import _clean_drug_rows
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event
from upande_livestock.serverscripts.common import herd_movement
from upande_livestock.serverscripts.common import stock as livestock_stock


@frappe.whitelist()
def create_drying_off_event(payload):
	"""Take a cow out of milk, and move her where the farm says dry cows go.

	THE DESTINATION IS A SETTING, NOT A HABIT. Livestock Settings holds the
	drying-off herd (falling back to the Steamer Herd, which is where they went
	before the field existed), and it is used when the caller names none — so
	the common case is one tap and the cow lands where the feed run expects her.

	A DIFFERENT HERD IS WARNED ABOUT AND THEN ACCEPTED. A farm moves a cow
	somewhere else for reasons this app does not know: a quarter it wants
	watched, a pen nearer the parlour, a gate that is broken this week.
	Refusing would send the herdsman to the desk to do it anyway, and the record
	would then say nothing about why. So the deviation is written onto the event
	and named in the answer, which is the part that is actually worth having.
	"""

	def go():
		guard("Livestock Event")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		doc = new_livestock_event(d, "Drying Off")
		suggested = herd_movement.dry_off_destination()
		chosen = d.get("new_herd") or suggested["herd"]
		if chosen:
			doc.new_herd = chosen
		note = herd_movement.dry_off_destination_note(chosen)
		if note:
			# On the record, not only in the answer: a month later the question
			# is why she went to the wrong pen, and a toast is long gone.
			doc.remarks = f"{doc.remarks}\n{note}".strip() if doc.remarks else note
		# Drying off a cow means sealing her quarters, so Livestock Event Type
		# flags it drug-consuming. The rows were being read off the payload by
		# nothing at all, which left the teat sealant on the shelf while the
		# ledger said the cow was dry.
		for drug in _clean_drug_rows(d.get("drugs"), d.get("source_warehouse") or livestock_stock.drug_warehouse()):
			doc.append("drug_issues", drug)
		doc.insert()
		doc.submit()  # LivestockEvent.on_submit posts the issue as "Animal Treatment"
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"stock_entry": doc.stock_entry or "",
			"new_herd": doc.new_herd,
			"suggested_herd": suggested["herd"],
			# Said rather than refused. The screen repeats it; the event carries it.
			"note": note,
		}

	return run(go, "livestock create_drying_off_event failed")
