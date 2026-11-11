"""Can a birth be recorded for this dam on this day — and if not, what then?

Asked by the calving screens the moment a dam and a date are picked, so the
rule (common/birth_window) is explained BEFORE the calves are typed in rather
than after the save is refused. Read-only; the same functions decide the save.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from upande_livestock.serverscripts.common import birth_window, herd_history
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run


@frappe.whitelist()
def birth_check(payload=None):
	"""{dam, birth_date?, service_date?} -> whether the birth may be recorded.

	`allowed` with `basis` ({kind: "diagnosis"|"service", service, service_date})
	when it may; otherwise the window, the service dates that would fit, and
	whether this user may take the retro path (`retro_allowed`, else
	`retro_refusal` says who can). With `service_date`, also the herd her
	history puts her in that day (`herd_on_service_date`) to start the picker on.
	"""

	def go():
		guard_read("Livestock Event")
		d = as_dict(payload)
		dam = d.get("dam") or d.get("animal")
		if not dam or not frappe.db.exists("Animal", dam):
			frappe.throw(_("Select the dam."))
		birth_date = str(getdate(d.get("birth_date") or d.get("event_date") or today()))
		found = birth_window.basis(dam, birth_date)
		out = {
			"ok": True,
			"allowed": bool(found),
			"basis": found,
			"message": "" if found else birth_window.refusal_message(dam, birth_date),
			"current_herd": frappe.db.get_value("Animal", dam, "current_herd") or "",
			**birth_window.details(dam, birth_date),
		}
		if d.get("service_date"):
			out["herd_on_service_date"] = herd_history.herd_on(dam, d["service_date"]) or ""
			out["service_date_fits"] = birth_window.fits(d["service_date"], birth_date)
		return out

	return run(go, "livestock birth_check failed")
