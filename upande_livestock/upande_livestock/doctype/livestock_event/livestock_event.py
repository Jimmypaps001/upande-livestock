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
from frappe.utils import flt, getdate, nowdate

from upande_livestock import livestock_stock

from upande_livestock.api.animal import create_calf
from upande_livestock.livestock_guards import check_guards
from upande_livestock.livestock_timings import get_timing


def warn_on_calving_mismatch(calving_name):
	"""Warn, never block, when a calving's expected and recorded birth counts
	disagree.

	A module-level function, not a method, so it has one caller-agnostic
	definition shared by both places that need it: LivestockEvent's own
	refresh_calving_birth_count (fired once per Birth submit/cancel outside a
	batch) and api.operations.record_calf_births (fired once after its whole
	multi-calf loop finishes, not per calf — see refresh_calving_birth_count's
	docstring for why per-calf would produce false alarms on an in-progress,
	ultimately-correct batch). Reads both counts fresh from the database rather
	than trusting an in-memory doc, since the caller may hold either the
	Calving or a Birth event.
	"""
	if not calving_name:
		return
	expected, recorded = frappe.db.get_value(
		"Livestock Event", calving_name, ["custom_no_of_calves", "births_recorded"]
	)
	expected = expected or 0
	recorded = recorded or 0
	if expected and recorded and expected != recorded:
		frappe.msgprint(
			_("This calving expects {0} calves but {1} Birth events are recorded.").format(
				expected, recorded
			),
			alert=True,
			indicator="orange",
		)


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

	def _type_creates_animal(self):
		if not self.event_type:
			return False
		return bool(frappe.db.get_value("Livestock Event Type", self.event_type, "creates_animal"))

	def create_calf_if_needed(self):
		"""For a Birth event with no animal yet, create the calf and point at it.

		This is the one place a calf Animal is created. api/operations.py's
		record_birth and record_calf_births both build a Birth event with `animal`
		left unset and let this method create it, rather than creating the Animal
		themselves — a second calf-creation path is what would let a form-booked
		or API-booked birth create the calf twice.
		"""
		if not self._type_creates_animal():
			return
		if self.animal:
			return
		if self.is_stillborn:
			return
		if not self.dam:
			frappe.throw(_("Select the dam for a Birth event."))

		self.animal = create_calf(
			dam=self.dam,
			tag_number=self.calf_tag_number,
			sex=self.calf_sex,
			event_date=self.event_date,
			birth_weight=self.calf_birth_weight_kg,
			burn_name=self.calf_burn_name,
			# An empty/unset calf_herd must still fall back to resolve_calf_herd()
			# inside create_calf() — only a real herd name should override it.
			herd=self.calf_herd or None,
		)

	def before_insert(self):
		self.create_calf_if_needed()

		# A stillborn Birth event has no calf to point at, so there is no Animal to
		# update. Everything below this line is per-animal status maintenance.
		if not self.animal:
			return

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
				existing_todo = frappe.db.exists(
					{
						"doctype": "ToDo",
						"reference_type": "Livestock Event",
						"reference_name": self.name,
						"status": ["!=", "Cancelled"],
					}
				)

				if not existing_todo:
					todo = frappe.get_doc(
						{
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
							"status": "Open",
						}
					)

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
					if animal.meta.has_field("expected_calving_date") and service.meta.has_field(
						"expected_calving_date"
					):
						animal.db_set(
							"expected_calving_date", service.expected_calving_date, update_modified=False
						)

					# Create calving alert
					if service.meta.has_field("expected_calving_date") and service.expected_calving_date:
						alert_date = frappe.utils.add_days(
							service.expected_calving_date, -get_timing("calving_alert_lead_days")
						)

						existing_calving_todo = frappe.db.exists(
							{
								"doctype": "ToDo",
								"reference_type": "Livestock Event",
								"reference_name": self.related_service,
								"description": ["like", "%Calving Expected%"],
								"status": ["!=", "Cancelled"],
							}
						)

						if not existing_calving_todo:
							todo = frappe.get_doc(
								{
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
									"status": "Open",
								}
							)
							todo.insert(ignore_permissions=True)
							pass

				elif self.diagnosis_result in ["Not Pregnant", "Aborted"]:
					service.db_set(
						"pregnancy_confirmation_status", self.diagnosis_result, update_modified=False
					)
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
				existing_rebreeding_todo = frappe.db.exists(
					{
						"doctype": "ToDo",
						"reference_type": "Livestock Event",
						"reference_name": self.name,
						"description": ["like", "%Ready for Re-breeding%"],
						"status": ["!=", "Cancelled"],
					}
				)

				if not existing_rebreeding_todo:
					todo = frappe.get_doc(
						{
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
							"status": "Open",
						}
					)
					todo.insert(ignore_permissions=True)
					pass

		# Movement herd update + herd-count recompute are handled solely by the
		# herd_movement_processor script. Doing it here (Before Insert) would pre-empt
		# that script and suppress its number_of_animals recompute, so it is omitted.

		# Commit all changes
		pass

	def validate(self):
		# ============================================================
		# CONDITIONAL MANDATORY: OPERATOR
		# ============================================================
		# operator carries mandatory_depends_on: "eval:!doc.reference_doctype"
		# in the DocType JSON (for the desk form's dynamic asterisk), but
		# Frappe's core Document._validate_mandatory() only ever checks
		# static reqd == 1 DocFields — mandatory_depends_on is a client-side
		# (desk UI) concept only and is never evaluated by server-side
		# insert()/submit(), including via the REST API, bench console, data
		# import or any other non-desk path. Without this explicit check, a
		# hand-entered event (no reference_doctype) could be created with no
		# operator through any of those paths, silently reintroducing the
		# exact class of gap this field was hardened against.
		if not self.reference_doctype and not self.operator:
			frappe.throw(
				_("{0} is mandatory for a hand-entered Livestock Event.").format(_("Operator(technician)")),
				frappe.MandatoryError,
			)

		# ============================================================
		# CONDITIONAL MANDATORY: ANIMAL
		# ============================================================
		# animal carries mandatory_depends_on: "eval:!doc.is_stillborn" in the
		# DocType JSON (for the desk form's dynamic asterisk), but — same as
		# operator above — mandatory_depends_on is a client-side (desk UI)
		# concept only and is never evaluated by server-side insert()/submit(),
		# including via the REST API, bench console, data import or any other
		# non-desk path. Without this explicit check, any event of any type
		# could be created with no animal through those paths.
		#
		# The only legitimate animal-less event is a stillborn Birth, so the
		# exemption is deliberately scoped to "this type creates animals AND
		# is_stillborn is set" rather than a bare "is_stillborn" check —
		# is_stillborn is only meaningful for Birth, and a bare check would let
		# a stillborn-flagged Feeding or Movement through animal-less too.
		#
		# create_calf_if_needed() runs in before_insert(), which the Frappe
		# insert() lifecycle runs before validate() — so for a non-stillborn
		# Birth, self.animal is already populated with the newly created calf
		# by the time this check runs.
		# A Feeding is the second legitimate animal-less event, and for a different
		# reason: feed is issued to a whole herd, not to one animal. Recording it per
		# animal would mean 119 identical rows for a single trough. The exemption is
		# scoped to "Feeding AND a herd is named" so it cannot become a way to save
		# an event with neither an animal nor a herd attached to anything.
		herd_level_feeding = self.event_type == "Feeding" and bool(self.current_herd)
		if (
			not self.animal
			and not (self._type_creates_animal() and self.is_stillborn)
			and not herd_level_feeding
		):
			frappe.throw(
				_("{0} is mandatory for this Livestock Event.").format(_("Animal")),
				frappe.MandatoryError,
			)

		# ============================================================
		# CONDITIONAL MANDATORY: CALF TAG / CALF SEX
		# ============================================================
		# calf_tag_number / calf_sex carry mandatory_depends_on, which Frappe
		# enforces only in the browser. A Birth event reaching us from the REST
		# API, data import or the mobile client would otherwise be accepted with
		# neither field set.
		if self._type_creates_animal() and not self.is_stillborn:
			if not self.calf_tag_number:
				frappe.throw(
					_("Calf Tag / Book Number is mandatory for a Birth event."),
					frappe.MandatoryError,
				)
			if self.calf_sex not in ("Female", "Male"):
				frappe.throw(
					_("Calf Sex must be Female or Male for a Birth event."),
					frappe.MandatoryError,
				)

		# ============================================================
		# CONDITIONAL MANDATORY: ABORTION CAUSE
		# ============================================================
		# abortion_cause carries mandatory_depends_on, which Frappe enforces only
		# in the browser (same gap as operator/animal/calf_tag_number/calf_sex
		# above). Without this, an Abortion event reaching us from the REST API,
		# data import or the mobile client could be recorded with no cause at all.
		if self.event_type == "Abortion" and not self.abortion_cause:
			frappe.throw(
				_("{0} is mandatory for an Abortion event.").format(_("Probable Cause")),
				frappe.MandatoryError,
			)

		# ============================================================
		# CLEAR-DETECTION: EVENT DATE (reject blanking a stored date)
		# ============================================================
		# event_date has no reqd/mandatory_depends_on in the DocType JSON at
		# all, but it does carry `"default": "Today"` — and
		# Document.insert() always calls _set_defaults() before validate()
		# ever runs, on every path. That means a brand-new document can
		# never actually reach this method with a blank event_date:
		# verified directly against this site — frappe.get_doc({...}) with
		# no event_date, frappe.get_doc({..., "event_date": None}),
		# doc.event_date = None set before insert(), and a
		# frappe.client.insert REST call with event_date: None were all
		# silently repopulated to today before validate() saw them. A
		# previous version of this block special-cased self.is_new() to
		# require event_date on new documents; that branch could never
		# fire and was dead code.
		#
		# The real gap is on UPDATE: the field default only reapplies while
		# a document is still new, so once a row exists, setting
		# event_date = None and calling save() persists the NULL —
		# verified the same way. That is exactly how the 5 NULL rows on
		# kaitet.local were produced: two of the three duplicate
		# Client-Script-era `frappe.ui.form.on("Livestock Event", ...)`
		# registrations in public/js/livestock_event.js unconditionally did
		# `frm.set_value("event_date", null)` on a later desk save. That JS
		# bug is fixed alongside this check, but the REST API, data import
		# and the mobile client never went through that JS at all, so a
		# structural, server-side guard on the update path is what actually
		# closes the gap.
		#
		# This matters beyond the missing date: livestock_guards.py's age
		# and interval rules return early whenever event_date is falsy, so
		# an event with no date silently escapes every guard this project
		# built.
		#
		# Reject only the transition that actually causes damage: a stored
		# date being cleared. self.get_doc_before_save() holds exactly the
		# pre-update row here — check_if_latest() (called from both
		# insert() and _save(), before run_before_save_methods() ever calls
		# validate()) always populates it ahead of validate() whenever this
		# is not a new document, and is None for a new/nonexistent
		# document, so this skips cleanly on insert with no separate
		# is_new() check needed. A row that is already NULL (the 3
		# remaining Calving rows with no recoverable date) is not being
		# cleared by this save, so nothing here blocks it from being
		# resaved.
		stored = self.get_doc_before_save()
		if stored and stored.event_date and not self.event_date:
			frappe.throw(
				_("{0} is mandatory for a Livestock Event.").format(_("Event Date")),
				frappe.MandatoryError,
			)

		# ============================================================
		# VALIDATION FOR SERVICE EVENTS
		# ============================================================

		if self.event_type == "Service":
			# Rule 1: No second service without feedback on first service
			pending_services = frappe.db.sql(
				"""
                SELECT name, service_date, pregnancy_confirmation_status
                FROM `tabLivestock Event`
                WHERE animal = %s
                AND event_type = 'Service'
                AND docstatus = 1
                AND pregnancy_confirmation_status = 'Pending'
                AND name != %s
                ORDER BY service_date DESC
                LIMIT 1
            """,
				(self.animal, self.name or "new"),
				as_dict=True,
			)

			if pending_services:
				last_service = pending_services[0]
				days_since = frappe.utils.date_diff(self.service_date, last_service.service_date)

				frappe.throw(f"""<b>⚠️ Cannot record new service!</b><br><br>
                    This animal has a pending service from <b>{frappe.utils.formatdate(last_service.service_date)}</b> ({days_since} days ago).<br>
                    <b>Action Required:</b> Complete pregnancy diagnosis for service <b>{last_service.name}</b> first.<br><br>
                    <i>Tip: Go to Livestock Events → Find service → Record pregnancy diagnosis</i>""")

			# Rule 2: Check if animal is already confirmed pregnant
			active_pregnancy = frappe.db.sql(
				"""
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
            """,
				(self.animal,),
				as_dict=True,
			)

			if active_pregnancy:
				pregnancy = active_pregnancy[0]
				expected_calving = pregnancy.get("expected_calving_date")
				days_until = (
					frappe.utils.date_diff(expected_calving, frappe.utils.nowdate())
					if expected_calving
					else 0
				)

				frappe.throw(f"""<b>🤰 Animal is Already Pregnant!</b><br><br>
                    Service Date: <b>{frappe.utils.formatdate(pregnancy.service_date)}</b><br>
                    Expected Calving: <b>{frappe.utils.formatdate(expected_calving) if expected_calving else 'Not set'}</b><br>
                    Days Until Calving: <b>{days_until}</b> days<br><br>
                    <b>Action:</b> Cannot service pregnant animals. Wait for calving.""")

			# Rule 3: Check post-partum waiting period
			last_calving = frappe.db.sql(
				"""
                SELECT name, event_date, custom_calving_outcome
                FROM `tabLivestock Event`
                WHERE animal = %s
                AND event_type = 'Calving'
                AND docstatus = 1
                ORDER BY event_date DESC
                LIMIT 1
            """,
				(self.animal,),
				as_dict=True,
			)

			if last_calving:
				calving = last_calving[0]
				days_since_calving = frappe.utils.date_diff(self.service_date, calving.event_date)
				minimum_days = get_timing("post_calving_min_service_days")
				optimal_days = get_timing("post_calving_optimal_service_days")

				if days_since_calving < minimum_days:
					frappe.throw(f"""<b>⚠️ Too Early for Service!</b><br><br>
                        Last Calving: <b>{frappe.utils.formatdate(calving.event_date)}</b> ({days_since_calving} days ago)<br>
                        Minimum Waiting Period: <b>{minimum_days} days</b><br>
                        Shortfall: <b>{minimum_days - days_since_calving} days</b><br><br>
                        <b>Reason:</b> Animal needs time for uterine involution and recovery.<br>
                        <b>Recommendation:</b> Wait at least {minimum_days} days post-calving.""")
				elif days_since_calving < optimal_days:
					frappe.msgprint(
						f"""<b>⚠️ Early Service Warning</b><br><br>
                        Days since calving: <b>{days_since_calving}</b><br>
                        Optimal waiting period: <b>{optimal_days} days</b><br><br>
                        <i>Note: Service is allowed but conception rates improve after {optimal_days} days.</i>""",
						alert=True,
						indicator="orange",
					)

			# Rule 4: post-abortion waiting period (0 disables it)
			abortion_wait = get_timing("post_abortion_min_service_days")
			if abortion_wait:
				last_abortion = frappe.db.sql(
					"""SELECT name, event_date FROM `tabLivestock Event`
					   WHERE animal = %s AND event_type = 'Abortion' AND docstatus = 1
					   ORDER BY event_date DESC LIMIT 1""",
					(self.animal,),
					as_dict=True,
				)
				if last_abortion:
					days_since = frappe.utils.date_diff(self.service_date, last_abortion[0].event_date)
					if days_since < abortion_wait:
						frappe.throw(
							_(
								"Too early for service. Last abortion was {0} ({1} days ago); "
								"this farm requires {2} days. Adjust "
								"Livestock Settings → Minimum Days to Service After Abortion to change this."
							).format(
								frappe.utils.formatdate(last_abortion[0].event_date),
								days_since,
								abortion_wait,
							)
						)

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
				recent_service = frappe.db.sql(
					"""
                    SELECT name, service_date
                    FROM `tabLivestock Event`
                    WHERE animal = %s
                    AND event_type = 'Service'
                    AND docstatus = 1
                    AND pregnancy_confirmation_status = 'Pending'
                    ORDER BY service_date DESC
                    LIMIT 1
                """,
					(self.animal,),
					as_dict=True,
				)

				if recent_service:
					self.related_service = recent_service[0].name
					frappe.msgprint(
						f"""Auto-linked to most recent service: <b>{recent_service[0].name}</b> from {frappe.utils.formatdate(recent_service[0].service_date)}""",
						alert=True,
						indicator="blue",
					)
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
			if days_since_service < get_timing("diagnosis_earliest_days"):
				frappe.msgprint(
					f"""<b>⚠️ Very Early Diagnosis</b><br><br>
                    Days since service: <b>{days_since_service}</b><br>
                    Recommended minimum: <b>{get_timing("diagnosis_earliest_days")} days</b><br><br>
                    <i>Note: Pregnancy detection accuracy is lower before 21 days.</i>""",
					alert=True,
					indicator="orange",
				)
			elif days_since_service > get_timing("diagnosis_latest_days"):
				frappe.msgprint(
					f"""<b>⚠️ Very Late Diagnosis</b><br><br>
                    Days since service: <b>{days_since_service}</b><br>
                    Recommended maximum: <b>{get_timing("diagnosis_latest_days")} days</b><br><br>
                    <i>Note: This diagnosis is overdue.</i>""",
					alert=True,
					indicator="red",
				)

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
				pregnancy = frappe.db.sql(
					"""
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
                """,
					(self.animal,),
					as_dict=True,
				)

				if pregnancy:
					self.custom_related_pregnancy = pregnancy[0].name
					frappe.msgprint(
						f"""Auto-linked to pregnancy from service: <b>{pregnancy[0].name}</b>""",
						alert=True,
						indicator="blue",
					)
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

				if gestation_days < get_timing("gestation_short_warning_days"):
					frappe.msgprint(
						f"""<b>⚠️ Short Gestation Period!</b><br><br>
                        Gestation Length: <b>{gestation_days} days</b><br>
                        Normal Range: <b>270-290 days</b><br><br>
                        <i>Note: This may indicate premature birth or abortion.</i>""",
						alert=True,
						indicator="orange",
					)
				elif gestation_days > get_timing("gestation_long_warning_days"):
					frappe.msgprint(
						f"""<b>⚠️ Long Gestation Period!</b><br><br>
                        Gestation Length: <b>{gestation_days} days</b><br>
                        Normal Range: <b>270-290 days</b><br><br>
                        <i>Note: Verify the dates are correct.</i>""",
						alert=True,
						indicator="orange",
					)

			# Validate calving outcome
			if not self.custom_calving_outcome:
				frappe.throw("Please select the calving outcome: Live Birth, Still Birth, or Abortion")

		# ============================================================
		# VALIDATION FOR ABORTION
		# ============================================================
		# Auto-link mirrors the Calving block above (same query shape: most
		# recent Confirmed Service with no Calving recorded against it), with
		# one deliberate difference: Calving THROWS when nothing resolves,
		# Abortion does not.
		#
		# Why the asymmetry is correct: a Calving's own math (parity,
		# gestation length) is meaningless without a real pregnancy behind it.
		# An Abortion's own math (gestation_days_at_loss, in
		# compute_abortion_dates()) is already optional — guarded by
		# `if self.custom_related_pregnancy` — so there is nothing that
		# breaks by proceeding unlinked.
		#
		# Why throwing here would not even close the deadlock this auto-link
		# exists to fix: this query is the mirror image of Service Rule 2's
		# own query (a Confirmed pregnancy with no linked Calving). If this
		# query finds nothing, there is, by construction, no such row for
		# Rule 2 to ever throw on for this animal — so refusing to save the
		# Abortion would protect nothing, while blocking a real loss from
		# ever being recorded for a cow whose confirmation paperwork (a
		# Pregnancy Diagnosis event) was never entered. That may be
		# legitimate data this app must not refuse.
		if self.event_type == "Abortion" and not self.custom_related_pregnancy:
			pregnancy = frappe.db.sql(
				"""
                SELECT name, service_date
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
            """,
				(self.animal,),
				as_dict=True,
			)

			if pregnancy:
				self.custom_related_pregnancy = pregnancy[0].name
				frappe.msgprint(
					f"""Auto-linked to pregnancy from service: <b>{pregnancy[0].name}</b>""",
					alert=True,
					indicator="blue",
				)
			else:
				frappe.msgprint(
					_(
						"No confirmed pregnancy found to link this Abortion to. Recording "
						"without a linked pregnancy — gestation length at loss will not be "
						"calculated."
					),
					alert=True,
					indicator="orange",
				)

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
			# Calculate expected calving date
			self.expected_calving_date = frappe.utils.add_days(
				self.service_date, get_timing("gestation_period_days")
			)

			# Calculate pregnancy check due date
			self.pregnancy_check_due_date = frappe.utils.add_days(
				self.service_date, get_timing("pregnancy_check_days_after_service")
			)

			# Calculate next expected heat if fails
			self.next_expected_heat = frappe.utils.add_days(self.service_date, get_timing("heat_cycle_days"))

		if self.event_type == "Calving" and self.event_date:
			# Calculate when ready for re-breeding
			self.ready_for_service_date = frappe.utils.add_days(
				self.event_date, get_timing("post_calving_optimal_service_days")
			)

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
						old_count = frappe.db.count(
							"Animal", {"current_herd": previous_herd, "docstatus": ["!=", 2]}
						)
						frappe.db.set_value("Herds", previous_herd, "number_of_animals", old_count)

					# Update NEW herd count
					new_count = frappe.db.count(
						"Animal", {"current_herd": self.new_herd, "docstatus": ["!=", 2]}
					)
					frappe.db.set_value("Herds", self.new_herd, "number_of_animals", new_count)

					frappe.msgprint(
						f"Animal {self.animal} successfully moved from {previous_herd or 'no herd'} to {self.new_herd}"
					)
				else:
					frappe.msgprint("No herd change detected")

			except Exception as e:
				frappe.log_error(message=str(e), title="Herd Movement Error")
				frappe.throw(f"Error: Could not update animal herd - {str(e)}")

		# ============================================================
		# AGE AND INTERVAL GUARDS
		# ============================================================
		# Not folded into the per-type blocks above: these seven rules apply
		# uniformly across event types (age at Service/Calving; interval at
		# Calving/Vaccination/Deworming/Hoof Trimming/Weight Recording) and are
		# the one piece of validation that must also bind for the REST API,
		# api/operations.record_birth, data import and the mobile client, not
		# just the desk form the rest of this method was ported from.
		self.compute_abortion_dates()
		check_guards(self)

	def compute_abortion_dates(self):
		"""Gestation length at loss, and when the dam may be served again."""
		if self.event_type != "Abortion":
			return

		if self.custom_related_pregnancy:
			service_date = frappe.db.get_value(
				"Livestock Event", self.custom_related_pregnancy, "service_date"
			)
			if service_date:
				self.gestation_days_at_loss = frappe.utils.date_diff(self.event_date, service_date)

		wait_days = get_timing("post_abortion_min_service_days")
		if wait_days:
			self.ready_for_service_date = frappe.utils.add_days(self.event_date, wait_days)

	def close_pregnancy_after_abortion(self):
		"""Reopen the dam and fail the lost service. Parity is NOT incremented."""
		if self.event_type != "Abortion":
			return

		animal = frappe.get_doc("Animal", self.animal)
		if animal.meta.has_field("repro_status"):
			animal.db_set("repro_status", "Open", update_modified=False)
		if animal.meta.has_field("custom_pregnancy_status"):
			animal.db_set("custom_pregnancy_status", "Not Pregnant", update_modified=False)
		if animal.meta.has_field("expected_calving_date"):
			animal.db_set("expected_calving_date", None, update_modified=False)

		if not self.custom_related_pregnancy:
			return

		service = frappe.get_doc("Livestock Event", self.custom_related_pregnancy)
		service.db_set("service_status", "Failed", update_modified=False)
		service.db_set("pregnancy_confirmation_status", "Aborted", update_modified=False)
		if service.meta.has_field("custom_status_after_test"):
			service.db_set("custom_status_after_test", "Failed", update_modified=False)
		service.add_comment("Info", text=f"Pregnancy lost — recorded by Abortion event {self.name}")

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
				limit=1,
			)

			if last_pregnancy:
				last_pregnancy_date = last_pregnancy[0].diagnosis_date

				# 2. Check if a Calving OR an Abortion closed out that pregnancy.
				# An Abortion ends a pregnancy exactly as a Calving does — it
				# just never produces a calf — so it must satisfy this rule the
				# same way, or the cow could be re-served after an Abortion
				# (per close_pregnancy_after_abortion / Service Rule 2) but her
				# next pregnancy could never be confirmed.
				closed = frappe.db.exists(
					"Livestock Event",
					{
						"animal": self.animal,
						"event_type": ["in", ["Calving", "Abortion"]],
						"event_date": [">", last_pregnancy_date],
						"docstatus": 1,
					},
				)

				if not closed:
					frappe.throw(
						f"🐄 {self.animal} is already pregnant.\n\n"
						"The cow must calve before a new pregnancy can be recorded."
					)

		self.refresh_calving_birth_count()
		self.close_pregnancy_after_abortion()
		self.post_stock_issue()

	def on_cancel(self):
		self.refresh_calving_birth_count()

	def _type_consumes_drugs(self):
		"""Whether this event type takes drugs out of a store.

		Read off Livestock Event Type rather than a tuple in code, so the farm can
		flag a new drug-consuming type — dry-cow therapy at Drying Off, calcium at
		Calving — without a deploy. Mirrors `creates_animal`.
		"""
		if not self.event_type:
			return False
		return bool(frappe.db.get_value("Livestock Event Type", self.event_type, "consumes_drugs"))

	def post_stock_issue(self):
		"""Issue whatever this event consumed out of stock.

		A drug-consuming type issues its `drug_issues` rows; a Service issues the
		semen straw. Both block when the store cannot cover them — see
		livestock_stock for why that reversed.

		Guarded by `self.stock_entry` so an amend or a re-submit cannot post a
		second issue for the same event. That guard is also how a batch issue
		works: api/operations posts one Material Issue for a whole herd's
		deworming and stamps it on every event, so each event finds it already
		set and does not post its own.
		"""
		if self.stock_entry:
			return

		# A mirror event does not own its stock. Livestock Diagnosis and Livestock
		# Health Case create one of these through sync_event_for purely to put
		# themselves on the animal's timeline; the drug rows and the Material Issue
		# live on the source document, which posts them itself. Without this the
		# mirror would warn "recorded with no drugs issued" for every check-up.
		if self.reference_doctype:
			return

		rows, what = [], None
		if self._type_consumes_drugs():
			what = self.event_type
			default_wh = livestock_stock.drug_warehouse()
			for row in self.drug_issues or []:
				rows.append(
					{
						"item_code": row.item_code,
						"qty": row.qty,
						"warehouse": row.source_warehouse or default_wh,
						"batch_no": row.batch_no,
						"uom": row.uom,
					}
				)
			if not rows:
				# The reason 93 vaccinations consumed nothing: an empty drug table
				# passed silently. It still saves — a procedure genuinely may use
				# nothing — but it no longer does so quietly.
				frappe.msgprint(
					_("{0} recorded with no drugs issued. Nothing was taken out of the store.").format(
						self.event_type
					),
					alert=True,
					indicator="orange",
				)
		elif self.event_type == "Service":
			what = "Service"
			item = self.semen_item or livestock_stock.default_semen_item()
			if item:
				rows.append(
					{
						"item_code": item,
						# A Service with no straw count still consumes one straw.
						"qty": flt(self.semen_qty) or 1,
						"warehouse": livestock_stock.semen_warehouse(),
					}
				)

		if not rows:
			return

		name = livestock_stock.issue_items(
			rows,
			remarks=f"Livestock {what} - {self.animal} - {self.name}",
			posting_date=self.event_date,
			employee=self.operator,
		)
		if name:
			self.db_set("stock_entry", name, update_modified=False)
			# Each drug row keeps its own pointer at the issue, which is what
			# Livestock Drug Issue.stock_entry_ref exists for.
			for row in self.drug_issues or []:
				if row.item_code:
					row.db_set("stock_entry_ref", name, update_modified=False)

	def refresh_calving_birth_count(self):
		"""Recount the Birth events linked to this event's related calving, and
		warn (never block) if that leaves the calving's recorded and expected
		counts disagreeing.

		The warning has to fire from here — a Birth event's own submit/cancel —
		rather than from the Calving's on_submit. A Calving must already be
		submitted, with births_recorded still 0, before any Birth event can even
		reference it via related_calving; and this method updates the parent via
		a raw db.set_value, which does not re-trigger the Calving's own
		on_submit. A check placed only on Calving submission could therefore
		never actually see a mismatch. This is a warning, not a throw: farms
		legitimately record calves the next morning, and blocking submission
		would push staff to falsify custom_no_of_calves instead.

		The count refresh below is unconditional — births_recorded must stay
		accurate after every single Birth submit or cancel, batch or not. Only
		the *message* is suppressed mid-batch: api.operations.record_calf_births
		sets frappe.flags.suppress_calving_mismatch_warning around its own loop,
		so that inserting calf 1 of an eventual 3 does not warn about a mismatch
		that the batch itself is about to resolve two calves later. A single
		Birth submitted or cancelled outside that loop — from the desk form, or
		via a one-calf record_calf_births call — still warns immediately, since
		flags.suppress_calving_mismatch_warning is unset (falsy) on that path.
		"""
		if not self.related_calving:
			return
		count = frappe.db.count(
			"Livestock Event",
			{"related_calving": self.related_calving, "event_type": "Birth", "docstatus": 1},
		)
		frappe.db.set_value(
			"Livestock Event", self.related_calving, "births_recorded", count, update_modified=False
		)

		if not frappe.flags.get("suppress_calving_mismatch_warning"):
			warn_on_calving_mismatch(self.related_calving)
