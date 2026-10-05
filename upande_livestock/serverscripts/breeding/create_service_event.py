"""Record a service (A.I. or natural), and the straw it used."""

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
	expected-calving / check-due / next-heat dates. Where Service posts stock
	(Settings → Stock) the straw goes through the items table and on_submit
	issues it; where it does not, the straw is recorded on the event's own
	fields — a calf's record reads its sire there — and nothing is issued.
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
			# Service posts stock: the straw goes through the items table like
			# every other event's items. A caller still sending only the old
			# straw fields has them turned into an item row, not dropped.
			if not d.get("items") and d.get("semen_item"):
				d["items"] = [{"item_code": d.get("semen_item"), "qty": flt(d.get("semen_qty")) or 1,
				               "source_warehouse": d.get("semen_warehouse") or None}]
			append_items(doc, d)
		else:
			# Service posts no stock here: the straw is recorded on the event's
			# own fields, where a calf's record finds its sire, and not issued.
			doc.semen_item = d.get("semen_item") or None
			doc.semen_qty = flt(d.get("semen_qty")) or 1
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
