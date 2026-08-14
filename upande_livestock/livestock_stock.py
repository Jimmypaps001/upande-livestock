# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Post Material Issues for the livestock flows that consume stock.

Vaccination, deworming, treatment and service all take something out of a store.
They share one entry point here so the employee attribution, the failure policy and
the remark format cannot drift apart between them.

TWO THINGS THIS MODULE DELIBERATELY DOES:

1. It attributes every issue to an Employee, in both `custom_employee` and the
   `custom_employee_data` child table. This is not a nicety — this site runs a
   "PPE Issuance Assignment Creation" script on every Material Issue that requires
   exactly one employee in `custom_employee_data`, so an issue without it does not
   save at all. api/feeding.py carries the same workaround.

2. It never commits. api/feeding.py and api/assets.py call frappe.db.commit()
   mid-flow, which breaks the caller's ability to roll back a partially failed
   operation — api/operations._run() relies on that rollback. Committing is the
   caller's business, or the request's.
"""

import frappe
from frappe import _
from frappe.utils import flt


def drug_warehouse():
	return frappe.db.get_single_value("Livestock Settings", "drug_warehouse")


def semen_warehouse():
	"""The semen store, falling back to the drug store when it is not set apart."""
	return frappe.db.get_single_value("Livestock Settings", "semen_warehouse") or drug_warehouse()


def default_semen_item():
	return frappe.db.get_single_value("Livestock Settings", "semen_item")


def _employee_for(employee=None):
	return employee or frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def issue_items(rows, remarks, company=None, posting_date=None, employee=None):
	"""Post one Material Issue covering `rows`; return the Stock Entry name.

	`rows` is a list of dicts with item_code, qty and warehouse (batch_no and uom
	optional). Rows with no item or a non-positive qty are dropped — a form that
	leaves a drug line blank should not fail, it should issue nothing for it. If
	nothing usable survives, no Stock Entry is created and None is returned.

	Raises on a genuine stock problem (no stock, closed period, missing warehouse).
	Callers that must survive that should use try_issue_items().
	"""
	usable = [r for r in (rows or []) if r.get("item_code") and flt(r.get("qty")) > 0]
	if not usable:
		return None

	missing_wh = [r["item_code"] for r in usable if not r.get("warehouse")]
	if missing_wh:
		frappe.throw(
			_(
				"No source warehouse for {0}. Set one on the row, or set the Drug Store in Livestock Settings."
			).format(", ".join(missing_wh))
		)

	company = (
		company
		or frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		or frappe.defaults.get_user_default("company")
	)
	if not company:
		frappe.throw(_("No company configured (Livestock Settings > Default Company)."))

	employee = _employee_for(employee)
	if not employee:
		frappe.throw(
			_("No Employee is linked to your user ({0}). Link one before issuing stock.").format(
				frappe.session.user
			)
		)

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Issue"
	se.purpose = "Material Issue"
	se.company = company
	if posting_date:
		se.set_posting_time = 1
		se.posting_date = posting_date
	# See the module docstring: the PPE script requires exactly one employee here.
	if se.meta.has_field("custom_employee"):
		se.custom_employee = employee
	if se.meta.has_field("custom_employee_data"):
		row = se.append("custom_employee_data", {})
		row.employee = employee
		row.employee_name = frappe.db.get_value("Employee", employee, "employee_name")

	for r in usable:
		item = se.append("items", {})
		item.item_code = r["item_code"]
		item.qty = flt(r["qty"])
		item.s_warehouse = r["warehouse"]
		if r.get("batch_no"):
			item.batch_no = r["batch_no"]
		if r.get("uom"):
			item.uom = r["uom"]

	se.remarks = remarks
	se.insert(ignore_permissions=True)
	se.submit()
	return se.name


def try_issue_items(rows, remarks, what, **kwargs):
	"""issue_items(), downgrading any failure to a warning. Returns name or None.

	The clinical or breeding record is worth more than the stock posting: an animal
	was vaccinated, treated or served whether or not the warehouse balance allows
	the issue to post. Losing that record because the store is short is the worse
	outcome, so the event saves and the user is told the issue did not post. This
	mirrors LivestockDisposal.post_asset_disposal().
	"""
	try:
		return issue_items(rows, remarks, **kwargs)
	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title=f"Livestock {what} stock issue failed")
		frappe.msgprint(
			_("{0} was recorded, but the stock issue did not post: {1}").format(what, str(e)),
			alert=True,
			indicator="orange",
		)
		return None
