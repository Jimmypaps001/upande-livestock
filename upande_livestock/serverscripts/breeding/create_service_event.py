"""Record a service (A.I. or natural), issuing the semen straw it consumes."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.event_items import consumes_items
from upande_livestock.serverscripts.common.events import new_livestock_event
from upande_livestock.serverscripts.husbandry._shared import append_items


@frappe.whitelist()
def create_service_event(payload):
	"""Record a Service / insemination.

	LivestockEvent.validate() enforces the breeding rules and stamps the
	expected-calving / check-due / next-heat dates; its on_submit issues the semen
	straw out of the semen store. The straw item falls back to Livestock Settings
	when the caller does not name one.
	"""

	def go():
		guard("Livestock Event")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		doc = new_livestock_event(d, "Service", date_key="service_date")
		doc.service_type = d.get("service_type")
		doc.service_date = d.get("service_date") or today()
		doc.sire = d.get("sire")
		if consumes_items("Service"):
			# The farm mapped Service to an item group: the straw goes through
			# the same table as every other event's items, and the three legacy
			# fields are left alone (they are still READ for history, and by
			# record_birth to find a calf's sire on old services).
			append_items(doc, d)
		else:
			# No straws-only group to map Service to: the straw picker as it has
			# always worked. Which path a site takes is the mapping's answer.
			doc.semen_item = d.get("semen_item") or None
			doc.semen_qty = flt(d.get("semen_qty")) or 1
			# Blank is allowed and means "wherever the settings say"; the posting
			# falls back for us rather than this guessing a store.
			doc.semen_warehouse = d.get("semen_warehouse") or None
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"expected_calving_date": str(doc.expected_calving_date or ""),
			"pregnancy_check_due_date": str(doc.pregnancy_check_due_date or ""),
			"stock_entry": doc.stock_entry or "",
		}

	return run(go, "livestock create_service_event failed")
