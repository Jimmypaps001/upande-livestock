# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A treatment, dipping, deworming or vaccination given to a number of a shoat herd.

Submitting issues the drug from the Drug Store on the herd's cost centre (dose x number treated, in the
product's stock unit); cancelling takes the issue back.
"""

import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate, today

from upande_livestock.serverscripts.common import shoats


class HerdTreatment(Document):
	def validate(self):
		if not shoats.is_by_number(self.herd):
			frappe.throw(_("{0} is not counted by number.").format(self.herd))
		if getdate(self.treatment_date) > getdate(today()):
			frappe.throw(_("The date cannot be in the future."))
		if self.treatment_type not in shoats.TREATMENT_TYPES:
			frappe.throw(_("Type must be one of: {0}.").format(", ".join(shoats.TREATMENT_TYPES)))
		if cint(self.number_treated) <= 0:
			frappe.throw(_("Say how many animals were treated."))
		if flt(self.dose_per_head) <= 0:
			frappe.throw(_("Give the dose per head."))
		if cint(self.withdrawal_days) < 0:
			frappe.throw(_("Withdrawal cannot be negative."))
		head = shoats.head_on(self.herd, self.treatment_date)["total"]
		if cint(self.number_treated) > head:
			frappe.throw(_("{0} treated, but {1} only had {2} on {3}.").format(
				self.number_treated, self.herd, head, frappe.utils.formatdate(self.treatment_date)))
		self.quantity = round(cint(self.number_treated) * flt(self.dose_per_head), 4)
		uom = frappe.db.get_value("Item", self.product, "stock_uom")
		if uom and frappe.db.get_value("UOM", uom, "must_be_whole_number"):
			# vials and tubes are opened whole: issue the next whole unit
			self.quantity = float(math.ceil(self.quantity - 1e-9))
		self.withdrawal_end = (add_days(getdate(self.treatment_date), cint(self.withdrawal_days))
		                       if cint(self.withdrawal_days) else None)
		self.warehouse = self.warehouse or drug_store()
		if not self.warehouse:
			frappe.throw(_("There is no Drug Store to issue from."))

	def on_submit(self):
		from upande_livestock.serverscripts.common import stock as livestock_stock
		from upande_livestock.serverscripts.common.company import company_or_throw
		from upande_livestock.serverscripts.common.cost_center import resolve

		ensure_entry_type()
		company = company_or_throw(None)
		self.db_set("cost_center", resolve(company=company, herd=self.herd) or "", update_modified=False)
		name = livestock_stock.issue_items(
			[{"item_code": self.product, "qty": self.quantity, "warehouse": self.warehouse}],
			_("{0}: {1} x {2} {3} of {4} on {5}").format(
				_(self.treatment_type), self.number_treated, self.dose_per_head, self.dose_uom or "",
				self.product_name or self.product, self.herd),
			company=company, posting_date=str(self.treatment_date), employee=self.treated_by or self.operator_employee(),
			what="Shoat Treatment", herd=self.herd, draft_if_short=True)
		if name:
			self.db_set("stock_entry", name, update_modified=False)
		shoats.rebuild(self.herd)

	def operator_employee(self):
		return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name") or \
			frappe.db.get_value("Employee", {"status": "Active"}, "name")

	def on_cancel(self):
		if self.stock_entry and frappe.db.exists("Stock Entry", self.stock_entry):
			se = frappe.get_doc("Stock Entry", self.stock_entry)
			se.flags.ignore_permissions = True
			if se.docstatus == 1:
				se.cancel()
			elif se.docstatus == 0:
				frappe.delete_doc("Stock Entry", se.name, ignore_permissions=True, force=True)
				self.db_set("stock_entry", None, update_modified=False)
		shoats.rebuild(self.herd)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw(_("Cancel it first."))


def drug_store():
	"""The Drug Store to issue from: Livestock Settings' drug warehouse, else "Drug Store - <abbr>" of the
	default company."""
	from upande_livestock.serverscripts.common.company import default_company

	set_to = frappe.db.get_single_value("Livestock Settings", "drug_warehouse") \
		if frappe.get_meta("Livestock Settings").has_field("drug_warehouse") else None
	if set_to and frappe.db.exists("Warehouse", set_to):
		return set_to
	company = default_company()
	abbr = frappe.db.get_value("Company", company, "abbr") if company else None
	for name in (f"Drug Store - {abbr}", f"Livestock Drug Store - {abbr}"):
		if abbr and frappe.db.exists("Warehouse", name):
			return name
	return None


def ensure_entry_type():
	"""The stock entry type this issue posts under (a Material Issue named for it)."""
	name = "Livestock Shoat Treatment"
	if not frappe.db.exists("Stock Entry Type", name):
		doc = frappe.new_doc("Stock Entry Type")
		doc.name = name
		doc.purpose = "Material Issue"
		doc.is_standard = 0
		doc.insert(ignore_permissions=True)
