# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class MilkRecording(Document):
	def validate(self):
		# The whole point of a milk record is the amount milked. Frappe's `reqd`
		# lets a numeric 0 through, so guard the actual value: no record may be
		# saved/submitted without a positive yield for the herd milked.
		if flt(self.total_yield_kg) <= 0:
			frappe.throw(
				"Enter the amount of milk produced (Total Yield must be greater than 0)."
			)
		# Compute the derived (read-only) figures server-side so every entry path
		# — desk form, the Operations block, or the API — is consistent and the
		# after-submit Stock Entry always has a correct net_yield_kg.
		self.net_yield_kg = flt(self.total_yield_kg) - flt(self.discarded_kg)
		self.milk_revenue = flt(self.net_yield_kg) * flt(self.price_per_kg)

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
		se_type = frappe.db.get_single_value("Livestock Settings", "custom_milking_stock_entry_type") or "Milking"
		income_acct = self.income_account
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

		# 1. Stock Entry (type Milking) — carries the milking session + cows milked
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = se_type
		se.company = company
		se.posting_date = self.recording_date
		se.posting_time = "00:00:00"
		se.custom_milking_session = self.session
		se.custom_cows_milked = self.cows_milked
		se.remarks = "Milk Recording - {0} - {1} - {2}".format(self.herd, self.session, self.recording_date)

		if net_yield > 0:
			r1 = se.append("items", {})
			r1.item_code = milk_item
			r1.qty = net_yield
			r1.t_warehouse = target_wh
			if cost_center:
				r1.cost_center = cost_center

		if discarded > 0 and discard_wh:
			r2 = se.append("items", {})
			r2.item_code = milk_item
			r2.qty = discarded
			r2.t_warehouse = discard_wh
			if cost_center:
				r2.cost_center = cost_center

		try:
			se.insert(ignore_permissions=True)
			se.submit()
			frappe.db.set_value("Milk Recording", self.name, "stock_entry", se.name)
		except Exception as e:
			frappe.log_error("Milk Recording", "Stock Entry creation failed: " + str(e))

		# 2. Revenue JE (best-effort — skipped unless an income account is configured)
		if revenue > 0 and income_acct and credit_acct:
			try:
				je = frappe.new_doc("Journal Entry")
				je.company = company
				je.posting_date = self.recording_date
				je.user_remark = "Milk sales - {0} - {1} - {2} kg".format(self.herd, self.session, net_yield)
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
				frappe.log_error("Milk Recording", "Revenue JE failed: " + str(e))

		se_ref = frappe.db.get_value("Milk Recording", self.name, "stock_entry") or "pending"
		frappe.msgprint(
			"Stock Entry " + se_ref + " created. " + str(net_yield) + " kg milk posted."
			+ (" Revenue KES " + str(int(revenue)) + "." if revenue > 0 else ""),
			indicator="green",
			title="Milk Recording submitted",
		)

