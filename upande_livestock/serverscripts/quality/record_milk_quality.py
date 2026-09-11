# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Put the creamery's figures onto a milking that has already been recorded."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common import quality
from upande_livestock.serverscripts.common.envelope import as_dict, run


@frappe.whitelist()
def record_milk_quality(payload):
	"""Write lab results against a submitted Milk Recording.

	It writes to a SUBMITTED document, which is why those four fields carry
	allow_on_submit. That is not a loophole: a lab figure posts nothing — no
	stock, no journal, no guard reads it — so amending one cannot put the
	ledger out. The quantities on the same document, which do post, stay sealed
	by the submit exactly as before.
	"""

	def go():
		if not frappe.has_permission("Milk Recording", "write"):
			frappe.throw(_("You are not permitted to record milk quality."), frappe.PermissionError)

		d = as_dict(payload)
		name = (d.get("recording") or "").strip()
		if not name:
			frappe.throw(_("Select the milking this result belongs to."))
		if not frappe.db.exists("Milk Recording", name):
			frappe.throw(_("{0} is not a milk recording.").format(name))

		doc = frappe.get_doc("Milk Recording", name)
		if doc.docstatus == 2:
			frappe.throw(_("{0} was cancelled — there is nothing to attach a result to.").format(name))

		if not quality.has_readings(d):
			frappe.throw(
				_("Enter at least one figure — the bulk tank SCC, the fat or the protein. "
				  "Saving an empty result would clear the chase without answering it.")
			)

		for field in quality.LAB_FIELDS:
			if d.get(field) not in (None, ""):
				doc.db_set(field, flt(d.get(field)) or None, update_modified=False)
		doc.db_set("lab_test_date", d.get("lab_test_date") or today(), update_modified=False)
		if d.get("remarks"):
			doc.db_set("remarks", d.get("remarks"), update_modified=False)

		doc.reload()
		quality.stamp_pending(doc)
		doc.reload()

		ceiling = quality.scc_ceiling()
		return {
			"ok": True,
			"name": doc.name,
			"bulk_scc": doc.bulk_scc,
			"fat_percent": doc.fat_percent,
			"protein_percent": doc.protein_percent,
			"lab_test_date": str(doc.lab_test_date or ""),
			"over_ceiling": bool(ceiling and flt(doc.bulk_scc) > ceiling),
			"still_pending": bool(doc.get("custom_quality_pending")),
		}

	return run(go, "livestock record_milk_quality failed")
