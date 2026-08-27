# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


def _item_account(item_code, company, fieldname):
	"""Resolve an item's account the way Frappe 16 does: Item Defaults, then the
	Item Group's defaults. Returns None when neither level defines it.

	Kept as a module function rather than a method so api/operations.py and the
	drug/feed flows can reuse the same resolution order.
	"""
	if not (item_code and company):
		return None
	value = frappe.db.get_value(
		"Item Default",
		{"parent": item_code, "parenttype": "Item", "company": company},
		fieldname,
	)
	if value:
		return value
	item_group = frappe.db.get_value("Item", item_code, "item_group")
	if not item_group:
		return None
	return frappe.db.get_value(
		"Item Default",
		{"parent": item_group, "parenttype": "Item Group", "company": company},
		fieldname,
	)


class MilkRecording(Document):
	def validate(self):
		# The whole point of a milk record is the amount milked. Frappe's `reqd`
		# lets a numeric 0 through, so guard the actual value: no record may be
		# saved/submitted without a positive yield for the herd milked.
		if flt(self.total_yield_kg) <= 0:
			frappe.throw("Enter the amount of milk produced (Total Yield must be greater than 0).")
		# Compute the derived (read-only) figures server-side so every entry path
		# — desk form, the Operations block, or the API — is consistent and the
		# after-submit Stock Entry always has a correct net_yield_kg.
		self.net_yield_kg = flt(self.total_yield_kg) - flt(self.discarded_kg)
		self.milk_revenue = flt(self.net_yield_kg) * flt(self.price_per_kg)

		# Milk poured away is a loss, and a loss with no reason recorded cannot be
		# reduced. mandatory_depends_on covers the desk form; this covers the API
		# and the Operations block, which do not evaluate it.
		if flt(self.discarded_kg) > 0 and not self.get("discard_reason"):
			frappe.throw("Say why {0} kg was discarded — it is a loss, and an unexplained "
			             "loss cannot be acted on.".format(flt(self.discarded_kg)))
		if self.get("discard_reason") == "Other" and not self.get("discard_reason_notes"):
			frappe.throw("Describe the reason for the discard.")

	def on_submit(self):
		"""Post the milk into stock (+ a best-effort revenue Journal Entry).

		Ported from the "Milk Recording After Submit - Stock Entry" Server Script.
		Item / warehouses / stock-entry-type / accounts all come from Livestock
		Settings or this record — no hardcoded company or warehouse."""
		company = frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		milk_item = frappe.db.get_single_value("Livestock Settings", "custom_milk_item")
		target_wh = self.target_warehouse or frappe.db.get_single_value(
			"Livestock Settings", "custom_milk_target_warehouse"
		)
		se_type = (
			frappe.db.get_single_value("Livestock Settings", "custom_milking_stock_entry_type") or "Milking"
		)
		# Frappe 16 resolves an item's accounts from its Item Defaults, falling back to
		# its Item Group's — so when the record does not name an income account, look
		# it up the same way rather than silently skipping the revenue JE (which is
		# what happened before: income_account is not a required field and nothing
		# ever populated it).
		income_acct = self.income_account or _item_account(milk_item, company, "income_account")
		credit_acct = frappe.db.get_single_value("Livestock Settings", "custom_default_credit_account")
		cost_center = self.cost_center
		net_yield = flt(self.net_yield_kg)
		discarded = flt(self.discarded_kg)
		revenue = flt(self.milk_revenue)
		discard_wh = self.discard_warehouse or frappe.db.get_single_value(
			"Livestock Settings", "custom_milk_discard_warehouse"
		)

		if not milk_item:
			frappe.throw("Milk item not set in Livestock Settings (custom_milk_item).")
		if not target_wh:
			frappe.throw("Milk target warehouse not set in Livestock Settings or on this record.")

		# 1. Stock Entry (type Milking) — carries the milking time + cows milked.
		# The recording's own clock time is the posting time, so two milkings on the
		# same day land in the right stock order instead of both at midnight.
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = se_type
		se.company = company
		se.posting_date = self.recording_date
		se.posting_time = self.milking_time or "00:00:00"
		se.custom_milking_time = self.milking_time
		se.custom_cows_milked = self.cows_milked
		se.remarks = "Milk Recording - {0} - {1} - {2}".format(
			self.herd, self.milking_time, self.recording_date
		)

		# A Material Receipt of milk needs a valuation, and milk has no purchase price
		# — it is produced by the herd. The Item's own valuation_rate is the standard
		# cost to use; when a site has not set one, the row is flagged
		# allow_zero_valuation_rate so the receipt still posts. Without either, ERPNext
		# throws "Valuation Rate for the Item ... is required" and the whole Stock
		# Entry is lost.
		valuation = flt(frappe.db.get_value("Item", milk_item, "valuation_rate"))

		def _milk_row(qty, warehouse):
			row = se.append("items", {})
			row.item_code = milk_item
			row.qty = qty
			row.t_warehouse = warehouse
			if valuation > 0:
				row.basic_rate = valuation
			else:
				row.allow_zero_valuation_rate = 1
			if cost_center:
				row.cost_center = cost_center
			return row

		if net_yield > 0:
			_milk_row(net_yield, target_wh)

		if discarded > 0 and discard_wh:
			_milk_row(discarded, discard_wh)

		try:
			se.insert(ignore_permissions=True)
			se.submit()
			frappe.db.set_value("Milk Recording", self.name, "stock_entry", se.name)
		except Exception as e:
			# Previously this only wrote to the Error Log, so the user was told
			# "Stock Entry created" while no stock had moved at all. Tell them.
			frappe.log_error(
				message=frappe.get_traceback(), title="Milk Recording Stock Entry creation failed"
			)
			frappe.msgprint(
				"The milk was recorded but no stock was posted: {0}".format(str(e)),
				alert=True,
				indicator="red",
				title="Stock Entry failed",
			)

		# 2. Revenue JE (best-effort — skipped unless an income account is configured)
		if revenue > 0 and income_acct and credit_acct:
			try:
				je = frappe.new_doc("Journal Entry")
				je.company = company
				je.posting_date = self.recording_date
				je.user_remark = "Milk sales - {0} - {1} - {2} kg".format(
					self.herd, self.milking_time, net_yield
				)
				cr = je.append("accounts", {})
				cr.account = income_acct
				cr.credit_in_account_currency = revenue
				if cost_center:
					cr.cost_center = cost_center
				dr = je.append("accounts", {})
				dr.account = credit_acct
				dr.debit_in_account_currency = revenue
				je.insert(ignore_permissions=True)
				je.submit()
				frappe.db.set_value("Milk Recording", self.name, "journal_entry", je.name)
			except Exception as e:
				frappe.log_error(message=frappe.get_traceback(), title="Milk Recording revenue JE failed")
				frappe.msgprint(
					"The milk was recorded but the revenue Journal Entry did not post: {0}".format(str(e)),
					alert=True,
					indicator="orange",
					title="Revenue JE failed",
				)

		se_ref = frappe.db.get_value("Milk Recording", self.name, "stock_entry")
		if not se_ref:
			# Do not claim a Stock Entry that does not exist; the failure above already
			# said what went wrong.
			return
		frappe.msgprint(
			"Stock Entry "
			+ se_ref
			+ " created. "
			+ str(net_yield)
			+ " kg milk posted."
			+ (" Revenue KES " + str(int(revenue)) + "." if revenue > 0 else ""),
			indicator="green",
			title="Milk Recording submitted",
		)
