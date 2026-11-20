# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""record_quality_test: split out of quality.quality_tests; that module still re-exports it, so the old dotted path resolves."""

from frappe import _
import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common import milk_quality_test as mq
from upande_livestock.serverscripts.common import quality
from upande_livestock.serverscripts.quality.milk_batches import batch_recordings


@frappe.whitelist()
def record_quality_test(payload):
	"""Create a Milk Quality Test. `client_ref` makes it safe to send twice: a
	phone that never saw the reply and retries gets the first record back."""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.quality.quality_tests import DT, _full


	def go():
		guard(DT)
		d = as_dict(payload)
		ref = (d.get("client_ref") or "").strip()[:140]
		if ref:
			existing = frappe.db.get_value(DT, {"client_ref": ref}, "name")
			if existing:
				return _full(existing, duplicate=True)

		values = mq.clean(d)
		doc = frappe.new_doc(DT)
		doc.sample_date = mq.check_date(d.get("sample_date"))
		doc.shift = values.pop("shift") or ""
		doc.sample_type = values.pop("sample_type") or "Bottle sample"
		for k, v in values.items():
			doc.set(k, v)
		doc.buyer = (d.get("buyer") or "").strip() or None
		if doc.buyer and not frappe.db.exists("Customer", doc.buyer):
			frappe.throw(_("{0} is not a customer.").format(doc.buyer))
		doc.milk_recording = (d.get("milk_recording") or "").strip() or None
		doc.sensory_note = (d.get("sensory_note") or "").strip()[:140]
		doc.remarks = (d.get("remarks") or "").strip()
		doc.lab_slip = (d.get("lab_slip") or "").strip() or None
		doc.client_ref = ref or None
		doc.insert()

		# The one quality form also feeds the old Milk Recording lab fields, so the
		# pending list, the SCC ceiling alert and the reports reading them keep working.
		# Every recording of the batch (date + shift across herds) gets the figures.
		listed = d.get("recordings")
		if isinstance(listed, str):
			listed = [x.strip() for x in listed.split(",")]
		targets = list(listed or []) if listed else batch_recordings(
			doc.sample_date, doc.shift, include=[doc.milk_recording]
		)
		if doc.milk_recording and doc.milk_recording not in targets:
			targets.append(doc.milk_recording)
		written = quality.write_back(
			targets,
			{
				"bulk_scc": doc.bulk_scc,
				"fat_percent": doc.butterfat_percent,
				"protein_percent": doc.protein_percent,
			},
			doc.sample_date,
		)
		out = _full(doc.name)
		out["recordings_updated"] = written
		return out

	return run(go, "livestock record_quality_test failed")
