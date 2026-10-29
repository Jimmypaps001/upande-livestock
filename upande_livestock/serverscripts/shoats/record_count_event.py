# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Record a head count, birth, death, purchase, sale, slaughter, transfer, weaning or mating for a shoat herd."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import backdate, shoats
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run

FIELDS = ("females", "males", "young", "others", "born_dead", "cause", "other_herd", "paddock", "reason", "amount",
          "mating_start", "mating_end", "mating", "remarks")


@frappe.whitelist()
def record_count_event(payload=None):
	def go():
		guard("Herd Count Event")
		d = as_dict(payload)
		herd = (d.get("herd") or "").strip()
		if not herd or not shoats.is_by_number(herd):
			frappe.throw(_("{0} is not a shoat herd.").format(herd))
		event_type = d.get("event_type")
		if event_type not in shoats.EVENT_TYPES:
			frappe.throw(_("Event must be one of: {0}.").format(", ".join(shoats.EVENT_TYPES)))
		on, back = backdate.resolve(d)
		backdate.assert_not_future(on)
		backdate.assert_allowed(back)
		doc = frappe.new_doc("Herd Count Event")
		doc.update({"herd": herd, "event_type": event_type, "event_date": on,
		            "operator": d.get("operator") or current_employee()})
		doc.update({k: d.get(k) for k in FIELDS if d.get(k) not in (None, "")})
		linked = None
		if event_type in ("Birth", "Weaning") and not doc.mating:
			linked = shoats.mating_for_birth(herd, on) if event_type == "Birth" else None
			if linked:
				doc.mating = linked
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		doc.reload()
		row = shoats.event_row(frappe.get_doc("Herd Count Event", doc.name))
		return {
			"ok": True,
			"created": {"count_event": doc.name, "paired_event": doc.paired_event or None},
			"event": row, "herd": herd, "head": shoats.head(herd),
			"variance": row["variance"], "expected_birth_date": row["expected_birth_date"],
			"mating": doc.mating or None, "mating_linked": bool(linked), "warnings": [],
		}

	return run(go, "livestock record_count_event failed")
