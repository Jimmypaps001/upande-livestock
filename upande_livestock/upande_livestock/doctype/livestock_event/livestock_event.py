# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Livestock Event controller.

Ported from sandboxed Frappe Server Scripts into real DocType-event hooks:
  - before_insert : "Updates animal status, creates alerts, and updates related events" (Before Insert)
  - validate      : "VALIDATION FOR SERVICE EVENTS" then "herd_movement_processor" (Before Save)
  - on_submit     : "Update Service from Diagnosis" then "Livestock Auto Journal Entry" (After Submit)

The sandboxed scripts used `doc` for the current document; here that is `self`.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import getdate, nowdate


class LivestockEvent(Document):
	def autoname(self):
		"""Name as TYPE-YEAR-#####, e.g. FEEDING-2026-00001.

		The animal is a field on this document, so it has no business being in the
		name. The year comes from event_date rather than today, so a backdated entry
		files under the year it happened.
		"""
		if not self.event_type:
			frappe.throw(_("Event Type is required to name a Livestock Event"))

		prefix = re.sub(r"[^A-Z0-9]+", "-", self.event_type.upper()).strip("-")
		year = getdate(self.event_date or nowdate()).year
		self.name = make_autoname(f"{prefix}-{year}-.#####")

	def before_insert(self):
		# ============================================================
		# UPDATE ANIMAL STATUS ON ASSET
		# ============================================================

		animal = frappe.get_doc("Animal", self.animal)

		if self.event_type == "Service":
			# Update reproductive status on Asset
			if animal.meta.has_field("repro_status"):
				animal.db_set("repro_status", "Served", update_modified=False)
			if animal.meta.has_field("last_service_date"):
				animal.db_set("last_service_date", self.service_date, update_modified=False)
			if animal.meta.has_field("custom_pregnancy_status"):
				animal.db_set("custom_pregnancy_status", "Pending Check", update_modified=False)

			# Create pregnancy check alert/reminder
			if self.pregnancy_check_due_date:
				existing_todo = frappe.db.exists({
					"doctype": "ToDo",
					"reference_type": "Livestock Event",
					"reference_name": self.name,
					"status": ["!=", "Cancelled"]
				})

				if not existing_todo:
					todo = frappe.get_doc({
						"doctype": "ToDo",
						"description": f"""<b>🔍 Pregnancy Check Due</b><br>
                            Animal: {self.animal}<br>
                            Service Date: {frappe.utils.formatdate(self.service_date)}<br>
                            Check Due: {frappe.utils.formatdate(self.pregnancy_check_due_date)}<br>
                            Event: {self.name}""",
						"reference_type": "Livestock Event",
						"reference_name": self.name,
						"assigned_by": frappe.session.user,
						"priority": "Medium",
						"date": self.pregnancy_check_due_date,
						"status": "Open"
					})

					# Assign to operator if exists
					if self.operator:
						operator_user = frappe.db.get_value("Employee", self.operator, "user_id")
						if operator_user:
							todo.allocated_to = operator_user

					todo.insert(ignore_permissions=True)
					pass

		if self.event_type == "Pregnancy Diagnosis":
			# Update the related service event
			if self.related_service:
				service = frappe.get_doc("Livestock Event", self.related_service)

				if self.diagnosis_result == "Confirmed":
					service.db_set("pregnancy_confirmation_status", "Confirmed", update_modified=False)
					service.db_set("service_status", "Successful", update_modified=False)
					service.db_set("pregnancy_confirmation_date", self.diagnosis_date, update_modified=False)
					if service.meta.has_field("custom_status_after_test"):
						service.db_set("custom_status_after_test", "Successful", update_modified=False)

					# Update animal to pregnant
					if animal.meta.has_field("repro_status"):
						animal.db_set("repro_status", "Pregnant", update_modified=False)
					if animal.meta.has_field("custom_pregnancy_status"):
						animal.db_set("custom_pregnancy_status", "Confirmed", update_modified=False)
					if animal.meta.has_field("expected_calving_date") and service.meta.has_field("expected_calving_date"):
						animal.db_set("expected_calving_date", service.expected_calving_date, update_modified=False)

					# Create calving alert
					if service.meta.has_field("expected_calving_date") and service.expected_calving_date:
						alert_date = frappe.utils.add_days(service.expected_calving_date, -7)

						existing_calving_todo = frappe.db.exists({
							"doctype": "ToDo",
							"reference_type": "Livestock Event",
							"reference_name": self.related_service,
							"description": ["like", "%Calving Expected%"],
							"status": ["!=", "Cancelled"]
						})

						if not existing_calving_todo:
							todo = frappe.get_doc({
								"doctype": "ToDo",
								"description": f"""<b>🐄 Calving Expected Soon</b><br>
                                    Animal: {self.animal}<br>
                                    Expected Date: {frappe.utils.formatdate(service.expected_calving_date)}<br>
                                    Service: {self.related_service}<br><br>
                                    <i>Prepare calving area and monitor closely.</i>""",
								"reference_type": "Livestock Event",
								"reference_name": self.related_service,
								"priority": "High",
								"date": alert_date,
								"status": "Open"
							})
							todo.insert(ignore_permissions=True)
							pass

				elif self.diagnosis_result in ["Not Pregnant", "Aborted"]:
					service.db_set("pregnancy_confirmation_status", self.diagnosis_result, update_modified=False)
					service.db_set("service_status", "Failed", update_modified=False)
					if service.meta.has_field("custom_status_after_test"):
						service.db_set("custom_status_after_test", "Failed", update_modified=False)

					# Update animal to open
					if animal.meta.has_field("repro_status"):
						animal.db_set("repro_status", "Open", update_modified=False)
					if animal.meta.has_field("custom_pregnancy_status"):
						animal.db_set("custom_pregnancy_status", "Not Pregnant", update_modified=False)

				# Add comment to service
				service.add_comment("Info", text=f"""Updated by Pregnancy Diagnosis: {self.name}""")
				pass

		if self.event_type == "Calving":
			# Update animal status
			if animal.meta.has_field("repro_status"):
				animal.db_set("repro_status", "Open", update_modified=False)
			if animal.meta.has_field("custom_pregnancy_status"):
				animal.db_set("custom_pregnancy_status", "Not Pregnant", update_modified=False)
			if animal.meta.has_field("last_calving_date"):
				animal.db_set("last_calving_date", self.event_date, update_modified=False)

			# Increment lactation number
			if animal.meta.has_field("parity"):
				current_lactation = animal.parity or 0
				animal.db_set("parity", current_lactation + 1, update_modified=False)

			# Create re-breeding alert
			if self.meta.has_field("ready_for_service_date") and self.ready_for_service_date:
				existing_rebreeding_todo = frappe.db.exists({
					"doctype": "ToDo",
					"reference_type": "Livestock Event",
					"reference_name": self.name,
					"description": ["like", "%Ready for Re-breeding%"],
					"status": ["!=", "Cancelled"]
				})

				if not existing_rebreeding_todo:
					todo = frappe.get_doc({
						"doctype": "ToDo",
						"description": f"""<b>🔄 Ready for Re-breeding</b><br>
                            Animal: {self.animal}<br>
                            Calved: {frappe.utils.formatdate(self.event_date)}<br>
                            Ready from: {frappe.utils.formatdate(self.ready_for_service_date)}<br><br>
                            <i>Animal has completed voluntary waiting period.</i>""",
						"reference_type": "Livestock Event",
						"reference_name": self.name,
						"priority": "Medium",
						"date": self.ready_for_service_date,
						"status": "Open"
					})
					todo.insert(ignore_permissions=True)
					pass

		# Movement herd update + herd-count recompute are handled solely by the
		# herd_movement_processor script. Doing it here (Before Insert) would pre-empt
		# that script and suppress its number_of_animals recompute, so it is omitted.

		# Commit all changes
		pass

	def validate(self):
		# ============================================================
		# VALIDATION FOR SERVICE EVENTS
		# ============================================================

		if self.event_type == "Service":
			# Rule 1: No second service without feedback on first service
			pending_services = frappe.db.sql("""
                SELECT name, service_date, pregnancy_confirmation_status
                FROM `tabLivestock Event`
                WHERE animal = %s
                AND event_type = 'Service'
                AND docstatus = 1
                AND pregnancy_confirmation_status = 'Pending'
                AND name != %s
                ORDER BY service_date DESC
                LIMIT 1
            """, (self.animal, self.name or "new"), as_dict=True)

			if pending_services:
				last_service = pending_services[0]
				days_since = frappe.utils.date_diff(self.service_date, last_service.service_date)

				frappe.throw(f"""<b>⚠️ Cannot record new service!</b><br><br>
                    This animal has a pending service from <b>{frappe.utils.formatdate(last_service.service_date)}</b> ({days_since} days ago).<br>
                    <b>Action Required:</b> Complete pregnancy diagnosis for service <b>{last_service.name}</b> first.<br><br>
                    <i>Tip: Go to Livestock Events → Find service → Record pregnancy diagnosis</i>""")

			# Rule 2: Check if animal is already confirmed pregnant
			active_pregnancy = frappe.db.sql("""
                SELECT ae.name, ae.service_date, ae.expected_calving_date
                FROM `tabLivestock Event` ae
                WHERE ae.animal = %s
                AND ae.event_type = 'Service'
                AND ae.pregnancy_confirmation_status = 'Confirmed'
                AND ae.docstatus = 1
                AND NOT EXISTS (
                    SELECT 1 FROM `tabLivestock Event` calving
                    WHERE calving.animal = ae.animal
                    AND calving.event_type = 'Calving'
                    AND calving.custom_related_pregnancy = ae.name
                    AND calving.docstatus = 1
                )
                ORDER BY ae.service_date DESC
                LIMIT 1
            """, (self.animal,), as_dict=True)

			if active_pregnancy:
				pregnancy = active_pregnancy[0]
				expected_calving = pregnancy.get("expected_calving_date")
				days_until = frappe.utils.date_diff(expected_calving, frappe.utils.nowdate()) if expected_calving else 0

				frappe.throw(f"""<b>🤰 Animal is Already Pregnant!</b><br><br>
                    Service Date: <b>{frappe.utils.formatdate(pregnancy.service_date)}</b><br>
                    Expected Calving: <b>{frappe.utils.formatdate(expected_calving) if expected_calving else 'Not set'}</b><br>
                    Days Until Calving: <b>{days_until}</b> days<br><br>
                    <b>Action:</b> Cannot service pregnant animals. Wait for calving.""")

			# Rule 3: Check post-partum waiting period
			last_calving = frappe.db.sql("""
                SELECT name, event_date, custom_calving_outcome
                FROM `tabLivestock Event`
                WHERE animal = %s
                AND event_type = 'Calving'
                AND docstatus = 1
                ORDER BY event_date DESC
                LIMIT 1
            """, (self.animal,), as_dict=True)

			if last_calving:
				calving = last_calving[0]
				days_since_calving = frappe.utils.date_diff(self.service_date, calving.event_date)
				minimum_days = 45
				optimal_days = 60

				if days_since_calving < minimum_days:
					frappe.throw(f"""<b>⚠️ Too Early for Service!</b><br><br>
                        Last Calving: <b>{frappe.utils.formatdate(calving.event_date)}</b> ({days_since_calving} days ago)<br>
                        Minimum Waiting Period: <b>{minimum_days} days</b><br>
                        Shortfall: <b>{minimum_days - days_since_calving} days</b><br><br>
                        <b>Reason:</b> Animal needs time for uterine involution and recovery.<br>
                        <b>Recommendation:</b> Wait at least {minimum_days} days post-calving.""")
				elif days_since_calving < optimal_days:
					frappe.msgprint(f"""<b>⚠️ Early Service Warning</b><br><br>
                        Days since calving: <b>{days_since_calving}</b><br>
                        Optimal waiting period: <b>{optimal_days} days</b><br><br>
                        <i>Note: Service is allowed but conception rates improve after {optimal_days} days.</i>""", alert=True, indicator="orange")

			# Set initial pregnancy status
			if not self.pregnancy_confirmation_status:
				self.pregnancy_confirmation_status = "Pending"

			if not self.service_status:
				self.service_status = "Pending"

		# ============================================================
		# VALIDATION FOR PREGNANCY DIAGNOSIS
		# ============================================================

		if self.event_type == "Pregnancy Diagnosis":
			# Must have related service
			if not self.related_service:
				# Try to auto-find most recent pending service
				recent_service = frappe.db.sql("""
                    SELECT name, service_date
                    FROM `tabLivestock Event`
                    WHERE animal = %s
                    AND event_type = 'Service'
                    AND docstatus = 1
                    AND pregnancy_confirmation_status = 'Pending'
                    ORDER BY service_date DESC
                    LIMIT 1
                """, (self.animal,), as_dict=True)

				if recent_service:
					self.related_service = recent_service[0].name
					frappe.msgprint(f"""Auto-linked to most recent service: <b>{recent_service[0].name}</b> from {frappe.utils.formatdate(recent_service[0].service_date)}""", alert=True, indicator="blue")
				else:
					frappe.throw("""<b>❌ No Related Service Found!</b><br><br>
                        This animal has no pending service to diagnose.<br><br>
                        <b>Action Required:</b><br>
                        1. Ensure a service event has been recorded<br>
                        2. Service must be submitted (not draft)<br>
                        3. Service must have 'Pending' pregnancy status<br><br>
                        <i>Tip: Record the service event first, then come back to record diagnosis.</i>""")

			# Validate timing
			service = frappe.get_doc("Livestock Event", self.related_service)

			if not service.service_date:
				frappe.throw(f"""Related service {self.related_service} has no service date!""")

			if frappe.utils.getdate(self.diagnosis_date) < frappe.utils.getdate(service.service_date):
				frappe.throw(f"""<b>⚠️ Invalid Diagnosis Date!</b><br><br>
                    Diagnosis Date: <b>{frappe.utils.formatdate(self.diagnosis_date)}</b><br>
                    Service Date: <b>{frappe.utils.formatdate(service.service_date)}</b><br><br>
                    Diagnosis cannot be before service date!""")

			days_since_service = frappe.utils.date_diff(self.diagnosis_date, service.service_date)

			# Check timing appropriateness
			if days_since_service < 21:
				frappe.msgprint(f"""<b>⚠️ Very Early Diagnosis</b><br><br>
                    Days since service: <b>{days_since_service}</b><br>
                    Recommended minimum: <b>21 days</b><br><br>
                    <i>Note: Pregnancy detection accuracy is lower before 21 days.</i>""", alert=True, indicator="orange")
			elif days_since_service > 70:
				frappe.msgprint(f"""<b>⚠️ Very Late Diagnosis</b><br><br>
                    Days since service: <b>{days_since_service}</b><br>
                    Recommended maximum: <b>70 days</b><br><br>
                    <i>Note: This diagnosis is overdue.</i>""", alert=True, indicator="red")

			# Validate diagnosis result
			if not self.diagnosis_result:
				frappe.throw("Please select a diagnosis result: Confirmed, Not Pregnant, or Aborted")

		# ============================================================
		# VALIDATION FOR CALVING
		# ============================================================

		if self.event_type == "Calving":
			# Must link to pregnancy
			if not self.custom_related_pregnancy:
				# Try to auto-find confirmed pregnancy
				pregnancy = frappe.db.sql("""
                    SELECT name, service_date, expected_calving_date
                    FROM `tabLivestock Event`
                    WHERE animal = %s
                    AND event_type = 'Service'
                    AND pregnancy_confirmation_status = 'Confirmed'
                    AND docstatus = 1
                    AND NOT EXISTS (
                        SELECT 1 FROM `tabLivestock Event` c
                        WHERE c.custom_related_pregnancy = `tabLivestock Event`.name
                        AND c.event_type = 'Calving'
                        AND c.docstatus = 1
                    )
                    ORDER BY service_date DESC
                    LIMIT 1
                """, (self.animal,), as_dict=True)

				if pregnancy:
					self.custom_related_pregnancy = pregnancy[0].name
					frappe.msgprint(f"""Auto-linked to pregnancy from service: <b>{pregnancy[0].name}</b>""", alert=True, indicator="blue")
				else:
					frappe.throw("""<b>❌ No Active Pregnancy Found!</b><br><br>
                        This animal has no confirmed pregnancy to calve from.<br><br>
                        <b>Action Required:</b><br>
                        1. Ensure a service has been recorded<br>
                        2. Pregnancy must be confirmed via diagnosis<br>
                        3. No previous calving recorded for this pregnancy<br><br>
                        <i>Tip: Complete the pregnancy confirmation first.</i>""")

			# Validate gestation length
			service = frappe.get_doc("Livestock Event", self.custom_related_pregnancy)
			if service.service_date:
				gestation_days = frappe.utils.date_diff(self.event_date, service.service_date)

				if gestation_days < 260:
					frappe.msgprint(f"""<b>⚠️ Short Gestation Period!</b><br><br>
                        Gestation Length: <b>{gestation_days} days</b><br>
                        Normal Range: <b>270-290 days</b><br><br>
                        <i>Note: This may indicate premature birth or abortion.</i>""", alert=True, indicator="orange")
				elif gestation_days > 300:
					frappe.msgprint(f"""<b>⚠️ Long Gestation Period!</b><br><br>
                        Gestation Length: <b>{gestation_days} days</b><br>
                        Normal Range: <b>270-290 days</b><br><br>
                        <i>Note: Verify the dates are correct.</i>""", alert=True, indicator="orange")

			# Validate calving outcome
			if not self.custom_calving_outcome:
				frappe.throw("Please select the calving outcome: Live Birth, Still Birth, or Abortion")

		# ============================================================
		# VALIDATION FOR MOVEMENT
		# ============================================================

		if self.event_type == "Movement":
			if not self.current_herd:
				# Get current herd from animal
				animal_herd = frappe.db.get_value("Animal", self.animal, "current_herd")
				if animal_herd:
					self.current_herd = animal_herd

			if not self.new_herd:
				frappe.throw("Please select the destination herd")

			if self.current_herd == self.new_herd:
				frappe.throw("Current herd and new herd cannot be the same!")

		# ============================================================
		# CALCULATE DATES FOR ALL EVENTS
		# ============================================================

		if self.event_type == "Service" and self.service_date:
			# Calculate expected calving date (280 days)
			self.expected_calving_date = frappe.utils.add_days(self.service_date, 280)

			# Calculate pregnancy check due date (35 days optimal)
			self.pregnancy_check_due_date = frappe.utils.add_days(self.service_date, 35)

			# Calculate next expected heat if fails (21-day cycle)
			self.next_expected_heat = frappe.utils.add_days(self.service_date, 21)

		if self.event_type == "Calving" and self.event_date:
			# Calculate when ready for re-breeding (60 days post-partum)
			self.ready_for_service_date = frappe.utils.add_days(self.event_date, 60)

		# ============================================================
		# HERD MOVEMENT PROCESSOR
		# ============================================================

		if self.event_type == "Movement" and self.animal and self.new_herd:
			try:
				# Get the previous herd BEFORE updating
				previous_herd = frappe.db.get_value("Animal", self.animal, "current_herd")

				# Only proceed if there's an actual herd change
				if previous_herd != self.new_herd:
					# Update the animal's current herd
					frappe.db.set_value("Animal", self.animal, "current_herd", self.new_herd)

					# Update OLD herd count (if there was a previous herd)
					if previous_herd:
						old_count = frappe.db.count("Animal", {"current_herd": previous_herd, "docstatus": ["!=", 2]})
						frappe.db.set_value("Herds", previous_herd, "number_of_animals", old_count)

					# Update NEW herd count
					new_count = frappe.db.count("Animal", {"current_herd": self.new_herd, "docstatus": ["!=", 2]})
					frappe.db.set_value("Herds", self.new_herd, "number_of_animals", new_count)

					frappe.msgprint(f"Animal {self.animal} successfully moved from {previous_herd or 'no herd'} to {self.new_herd}")
				else:
					frappe.msgprint("No herd change detected")

			except Exception as e:
				frappe.log_error(message=str(e), title="Herd Movement Error")
				frappe.throw(f"Error: Could not update animal herd - {str(e)}")

	def on_submit(self):
		# --------------------------------------------
		# RULE: Cow must calve before next pregnancy
		# --------------------------------------------

		if self.event_type == "Pregnancy Diagnosis" and self.diagnosis_result == "Confirmed":

			# 1. Get last confirmed pregnancy BEFORE this one
			last_pregnancy = frappe.db.get_list(
				"Livestock Event",
				filters={
					"animal": self.animal,
					"event_type": "Pregnancy Diagnosis",
					"diagnosis_result": "Confirmed",
					"docstatus": 1,
					"name": ["!=", self.name],
				},
				fields=["name", "diagnosis_date"],
				order_by="diagnosis_date desc",
				limit=1
			)

			if last_pregnancy:
				last_pregnancy_date = last_pregnancy[0].diagnosis_date

				# 2. Check if a Calving event happened AFTER that pregnancy
				calving = frappe.db.exists(
					"Livestock Event",
					{
						"animal": self.animal,
						"event_type": "Calving",
						"event_date": [">", last_pregnancy_date],
						"docstatus": 1
					}
				)

				if not calving:
					frappe.throw(
						f"🐄 {self.animal} is already pregnant.\n\n"
						"The cow must calve before a new pregnancy can be recorded."
					)

		# ============================================================
		# LIVESTOCK AUTO JOURNAL ENTRY
		# ============================================================
		# Auto-create a Journal Entry when an Livestock Event with an activity cost is submitted.
		if not self.custom_activity_cost or float(self.custom_activity_cost) <= 0:
			pass
		else:
			try:
				settings = frappe.get_doc("Livestock Settings")
				if not settings.custom_auto_create_journal_entry:
					pass
				else:
					company = settings.custom_default_company
					credit_account = settings.custom_default_credit_account
					if not company or not credit_account:
						frappe.msgprint("Livestock Settings: Company or Credit Account not set.", indicator="orange")
					else:
						asset_link = frappe.db.get_value("Animal", self.animal, "asset_link")
						animal_herd = frappe.db.get_value("Animal", self.animal, "current_herd")
						asset_data = None
						if asset_link:
							asset_data = frappe.db.get_value("Asset", asset_link, ["asset_category", "company"], as_dict=True)
						if not asset_data or not asset_data.asset_category:
							frappe.msgprint("Animal " + str(self.animal) + " has no linked Asset Category; JE skipped.", indicator="orange")
						else:
							je_company = asset_data.company or company
							cat_account = frappe.db.get_value(
								"Asset Category Account",
								{"parent": asset_data.asset_category, "company_name": je_company},
								["fixed_asset_account", "depreciation_expense_account"],
								as_dict=True,
							)
							if not cat_account:
								frappe.msgprint("No account row for " + str(je_company) + " in Asset Category.", indicator="orange")
							else:
								expense_account = cat_account.fixed_asset_account
								if not expense_account:
									frappe.msgprint("No Fixed Asset Account set.", indicator="orange")
								else:
									cost_center = None
									if animal_herd:
										cost_center = frappe.db.get_value("Herds", animal_herd, "cost_center")
									frappe.db.set_value("Livestock Event", self.name, "custom_expense_account", expense_account, update_modified=False)
									if cost_center:
										frappe.db.set_value("Livestock Event", self.name, "custom_cost_center", cost_center, update_modified=False)
									je = frappe.get_doc({
										"doctype": "Journal Entry",
										"voucher_type": "Journal Entry",
										"company": je_company,
										"posting_date": self.event_date or frappe.utils.today(),
										"user_remark": "Auto: " + str(self.event_type) + " - " + str(self.animal) + " [" + str(self.name) + "]",
										"accounts": [
											{"account": expense_account, "debit_in_account_currency": float(self.custom_activity_cost), "cost_center": cost_center or ""},
											{"account": credit_account, "credit_in_account_currency": float(self.custom_activity_cost), "cost_center": cost_center or ""},
										],
									})
									je.insert(ignore_permissions=True)
									je.submit()
									frappe.db.set_value("Livestock Event", self.name, "custom_journal_entry", je.name, update_modified=False)
									frappe.msgprint("JE " + str(je.name) + " created: KES " + str(self.custom_activity_cost), indicator="green")
			except Exception as e:
				frappe.log_error(message=str(e), title="Livestock Auto JE Error")
				frappe.msgprint("JE failed: " + str(e), indicator="red")
