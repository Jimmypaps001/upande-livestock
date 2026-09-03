"""Dry off a cow, ending her lactation."""

import frappe
from frappe import _

from upande_livestock.serverscripts.husbandry._shared import _clean_drug_rows
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event
from upande_livestock.serverscripts.common import stock as livestock_stock


@frappe.whitelist()
def create_drying_off_event(payload):
	def go():
		guard("Livestock Event")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		doc = new_livestock_event(d, "Drying Off")
		if d.get("new_herd"):
			doc.new_herd = d.get("new_herd")
		# Drying off a cow means sealing her quarters, so Livestock Event Type
		# flags it drug-consuming. The rows were being read off the payload by
		# nothing at all, which left the teat sealant on the shelf while the
		# ledger said the cow was dry.
		for drug in _clean_drug_rows(d.get("drugs"), d.get("source_warehouse") or livestock_stock.drug_warehouse()):
			doc.append("drug_issues", drug)
		doc.insert()
		doc.submit()  # LivestockEvent.on_submit posts the issue as "Animal Treatment"
		doc.reload()
		return {"ok": True, "name": doc.name, "stock_entry": doc.stock_entry or ""}

	return run(go, "livestock create_drying_off_event failed")
