"""Record observed heat."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event


@frappe.whitelist()
def create_heat_event(payload):
	"""Record a Heat Detection — an observation, nothing more.

	It consumes no stock and moves no animal, but it is the fact a service is
	timed off, so it needs a home of its own rather than being folded into the
	husbandry endpoint (whose types all carry a vet, a cost or a drug row).
	"""

	def go():
		guard("Livestock Event")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		doc = new_livestock_event(d, "Heat Detection")
		doc.insert()
		doc.submit()
		return {"ok": True, "name": doc.name}

	return run(go, "livestock create_heat_event failed")
