"""Record a milking session for a herd.

Guards Milk Recording. The Stock Entry and Journal Entry it posts are made by
the controller with ignore_permissions, so this is the one check that matters."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, nowtime, today

from upande_livestock.serverscripts.common import backdate, quality
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


def _captured_at(raw):
	try:
		return get_datetime(raw) if raw else None
	except Exception:
		return None


@frappe.whitelist()
def create_milk_recording(payload, from_handset=False):
	return record(payload, from_handset=from_handset)


def record(payload, from_handset=False, offline=False):
	"""Create and submit a Milk Recording.

	`offline` is not a parameter of the whitelisted entry point on purpose: only
	`mobile.record_milking` may ask for the one-day late-sync grace, so a REST
	caller of `create_milk_recording` cannot claim it."""

	def go():
		guard("Milk Recording")
		d = as_dict(payload)
		herd = d.get("herd")
		if not herd:
			frappe.throw(_("Select a herd."))
		total = flt(d.get("total_yield_kg"))
		if total <= 0:
			frappe.throw(_("Total yield must be greater than zero."))
		discarded = flt(d.get("discarded_kg"))
		net = total - discarded
		if net < 0:
			frappe.throw(_("Discarded milk cannot exceed the total yield."))
		price = flt(d.get("price_per_kg"))

		company = (
			d.get("company")
			or frappe.db.get_single_value("Livestock Settings", "custom_default_company")
			or frappe.defaults.get_user_default("company")
		)
		if not company:
			frappe.throw(_("No company configured (Livestock Settings > Default Company)."))

		doc = frappe.new_doc("Milk Recording")
		doc.herd = herd
		doc.milking_time = d.get("milking_time") or nowtime()
		recording_date, is_backdated = backdate.resolve(d, "recording_date")
		if offline and is_backdated and not backdate.window_open():
			# The one exception to a closed window: a milking taken on the phone
			# without signal may sync a day late. The test is the milking's own
			# date against server today; captured_at is audit and never trusted.
			if getdate(recording_date) < add_days(getdate(today()), -1):
				frappe.throw(
					_("This milking is more than a day old — ask the Livestock Manager "
					  "to open backdating, then retry.")
				)
		else:
			backdate.assert_allowed(is_backdated)
		if offline:
			doc.captured_offline = 1
			doc.captured_at = _captured_at(d.get("captured_at"))
		doc.recording_date = recording_date
		backdate.stamp(doc, is_backdated)
		doc.cows_milked = int(flt(d.get("cows_milked")))
		doc.operator = d.get("operator") or current_employee()
		doc.company = company
		doc.total_yield_kg = total
		doc.discarded_kg = discarded
		doc.discard_reason = d.get("discard_reason") or None
		doc.discard_reason_notes = d.get("discard_reason_notes") or None
		# net_yield_kg / milk_revenue are read-only on the form (a client script
		# fills them there); server-side we must set them before submit because
		# the after-submit Stock Entry uses net_yield_kg.
		doc.net_yield_kg = net
		doc.price_per_kg = price
		doc.milk_revenue = net * price
		doc.cost_center = frappe.db.get_value("Herds", herd, "cost_center")

		# Lab figures, when the farm takes them at the parlour. When it takes
		# them afterwards these are ignored even if a caller sends them, so the
		# setting is the single answer to "where does the SCC go" rather than a
		# suggestion any client can overrule.
		if quality.captured_at_milking():
			doc.bulk_scc = flt(d.get("bulk_scc")) or None
			doc.protein_percent = flt(d.get("protein_percent")) or None
			doc.fat_percent = flt(d.get("fat_percent")) or None
			if not quality.has_readings(d) and quality.required_at_milking() and not from_handset:
				frappe.throw(
					_("This farm records milk quality at milking. Enter the bulk tank "
					  "SCC, protein or fat before saving, or turn that requirement off "
					  "in Livestock Settings.")
				)

		doc.remarks = d.get("remarks")
		doc.insert()
		doc.submit()  # fires "Milk Recording After Submit - Stock Entry"
		# After submit, because the flag is written with db_set and the document
		# has to exist to carry it.
		quality.stamp_pending(doc)
		doc.reload()

		return {
			"ok": True,
			"name": doc.name,
			"net_yield_kg": net,
			"revenue": doc.milk_revenue,
			"stock_entry": doc.stock_entry,
			"journal_entry": doc.journal_entry,
			"quality_pending": bool(doc.get("custom_quality_pending")),
		}

	return run(go, "livestock create_milk_recording failed")
