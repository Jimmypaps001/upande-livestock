# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Write endpoints for the "Livestock Operations" desk workspace block.

These back the styled data-entry forms (Feed / Milking / Events / Breeding /
Parlour) that bring the mobile-only livestock operations onto the web. Read-only
dashboard stats live in ``workspace.py``; this module only *creates/records*.

Contract for every endpoint here:
  * ``@frappe.whitelist()`` — callable from the block's CSRF-guarded fetch.
  * Permission is checked against the *target* DocType (``frappe.has_permission``)
    so roles are respected — the form is visible to all workspace users but the
    action fails cleanly if the role lacks create rights.
  * The body is wrapped so a failure returns ``{"error": <clean message>}``
    (validation messages from the doctype Server Scripts are surfaced verbatim)
    rather than a raw 500 / stack trace.
  * Success returns ``{"ok": True, ...}``.

INSEMINATION INVARIANT — do not break:
  Service / insemination / pregnancy-diagnosis create an **Livestock Event only**.
  There is deliberately NO Stock Entry (no semen-straw / consumable inventory
  movement) in any breeding path here. The only flows in this module that touch
  Stock Entry are feed (feeding.py) and milking (Milk Recording's after-submit
  Server Script). Keep it that way.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, nowtime, today

from upande_livestock.api import feeding
from upande_livestock.upande_livestock.doctype.livestock_event.livestock_event import (
	warn_on_calving_mismatch,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _guard(doctype: str):
	"""Raise a clean PermissionError-style throw if the user can't create `doctype`."""
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(_("You are not permitted to create {0}.").format(doctype))


def _ok(payload):
	"""Coerce the whitelist arg (JSON string from fetch, or dict) to a dict."""
	if isinstance(payload, str):
		try:
			return json.loads(payload or "{}")
		except Exception:
			return {}
	return payload or {}


def _current_employee():
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def _employee_or_throw(employee=None):
	employee = employee or _current_employee()
	if not employee:
		frappe.throw(
			_("No Employee is linked to your user ({0}). Select an operator or link an Employee.").format(
				frappe.session.user
			)
		)
	return employee


def _select_options(doctype, fieldname):
	"""The non-empty Select options of a field, from meta (avoids hardcoding)."""
	field = frappe.get_meta(doctype).get_field(fieldname)
	if not field or not field.options:
		return []
	return [o for o in (field.options or "").split("\n") if o.strip()]


def _herd_label_map():
	return {h.name: (h.herd_name or h.name) for h in frappe.get_all("Herds", fields=["name", "herd_name"])}


def _animal_label(row):
	return row.get("tag_number") or row.get("burn_name") or row.get("name")


# A retired animal must never be offered as a data-entry target. retire_animal()
# (api/animal.py) sets `disabled` alongside the final status, and `disabled` is the
# canonical flag — it is also what Frappe's own link search honours. The status
# list is kept as a second predicate so an animal that reached a final status
# without being disabled, or was disabled by any other route, is excluded either
# way.
_RETIRED_STATUSES = ["Dead", "Deceased", "Sold", "Culled", "Disposed"]

_ANIMAL_FIELDS = ["name", "tag_number", "burn_name", "current_herd", "repro_status"]


def _active_animals():
	"""Every animal still eligible to receive an event, newest tag order."""
	return frappe.get_all(
		"Animal",
		filters=[["status", "not in", _RETIRED_STATUSES], ["disabled", "=", 0]],
		fields=_ANIMAL_FIELDS,
		order_by="tag_number asc",
		limit_page_length=5000,
	)


def _animal_choices(animals, labels):
	return [
		{
			"name": a.name,
			"label": _animal_label(a),
			"herd": a.current_herd,
			"herd_label": labels.get(a.current_herd or "", a.current_herd or ""),
			"repro": a.repro_status,
		}
		for a in animals
	]


def _default_company():
	"""The company to stamp on livestock documents.

	Livestock Settings wins so a farm can pin its own company, then the user's
	default, then the site-wide Global Defaults value — the same last resort
	patches/migrate_animals_off_asset.py uses. Without the Global Defaults step the
	health, weight and disposal forms fail with "No company configured" on any site
	that never filled in the livestock-specific setting.
	"""
	return (
		frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		or frappe.defaults.get_user_default("company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)


def _company_or_throw(company=None):
	company = company or _default_company()
	if not company:
		frappe.throw(_("No company configured (Livestock Settings > Default Company)."))
	return company


def _run(fn, log_title):
	"""Execute `fn`, returning its dict on success or {"error": msg} on failure."""
	try:
		return fn()
	except frappe.PermissionError as e:
		return {"error": str(e) or _("Not permitted.")}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=log_title)
		# Surface the doctype/Server-Script validation message (may be HTML).
		return {"error": str(e) or _("Operation failed.")}


# ===========================================================================
# FEED
# ===========================================================================


@frappe.whitelist()
def feed_options():
	def go():
		herds = frappe.get_all(
			"Herds",
			filters=[["bom", "is", "set"]],
			fields=["name", "herd_name", "number_of_animals", "bom"],
			order_by="herd_name asc",
		)
		return {
			"ok": True,
			"herds": [
				{
					"name": h.name,
					"label": h.herd_name or h.name,
					"heads": int(h.number_of_animals or 0),
					"bom": h.bom,
				}
				for h in herds
			],
		}

	return _run(go, "livestock feed_options failed")


@frappe.whitelist()
def feed_preview(herd):
	def go():
		info = feeding.get_herd_feed_info(herd)
		info["ok"] = True
		return info

	return _run(go, "livestock feed_preview failed")


@frappe.whitelist()
def manufacture_feed(herd):
	def go():
		_guard("Work Order")
		_guard("Stock Entry")
		res = feeding.manufacture_herd_feed(herd)
		res["ok"] = True
		return res

	return _run(go, "livestock manufacture_feed failed")


@frappe.whitelist()
def issue_feed(herd, qty, employee=None):
	def go():
		_guard("Stock Entry")
		res = feeding.feed_herd(herd, qty, employee=employee)
		res["ok"] = True
		return res

	return _run(go, "livestock issue_feed failed")


# ===========================================================================
# MILKING
# ===========================================================================


@frappe.whitelist()
def milking_options():
	def go():
		herds = frappe.get_all("Herds", fields=["name", "herd_name", "cost_center"], order_by="herd_name asc")
		return {
			"ok": True,
			"herds": [{"name": h.name, "label": h.herd_name or h.name} for h in herds],
			"sessions": _select_options("Milk Recording", "session"),
			"company": _default_company(),
			"employee": _current_employee(),
		}

	return _run(go, "livestock milking_options failed")


@frappe.whitelist()
def create_milk_recording(payload):
	def go():
		_guard("Milk Recording")
		d = _ok(payload)
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
		doc.session = d.get("session")
		doc.recording_date = d.get("recording_date") or today()
		doc.cows_milked = int(flt(d.get("cows_milked")))
		doc.operator = d.get("operator") or _current_employee()
		doc.company = company
		doc.total_yield_kg = total
		doc.discarded_kg = discarded
		# net_yield_kg / milk_revenue are read-only on the form (a client script
		# fills them there); server-side we must set them before submit because
		# the after-submit Stock Entry uses net_yield_kg.
		doc.net_yield_kg = net
		doc.price_per_kg = price
		doc.milk_revenue = net * price
		doc.cost_center = frappe.db.get_value("Herds", herd, "cost_center")
		doc.bulk_scc = flt(d.get("bulk_scc")) or None
		doc.fat_percent = flt(d.get("fat_percent")) or None
		doc.protein_percent = flt(d.get("protein_percent")) or None
		doc.remarks = d.get("remarks")
		doc.insert()
		doc.submit()  # fires "Milk Recording After Submit - Stock Entry"
		doc.reload()

		return {
			"ok": True,
			"name": doc.name,
			"net_yield_kg": net,
			"revenue": doc.milk_revenue,
			"stock_entry": doc.stock_entry,
			"journal_entry": doc.journal_entry,
		}

	return _run(go, "livestock create_milk_recording failed")


# ===========================================================================
# EVENTS  (Movement · Drying Off · Calving/Birth)
# ===========================================================================


@frappe.whitelist()
def event_options():
	def go():
		labels = _herd_label_map()
		animals = _active_animals()
		return {
			"ok": True,
			"animals": _animal_choices(animals, labels),
			"herds": [{"name": n, "label": l} for n, l in sorted(labels.items(), key=lambda x: x[1])],
			"calving_outcomes": _select_options("Livestock Event", "custom_calving_outcome")
			or ["Live Birth", "Still Birth"],
			"employee": _current_employee(),
		}

	return _run(go, "livestock event_options failed")


def _new_livestock_event(d, event_type, date_key=None):
	"""Build an unsaved Livestock Event of `event_type`.

	`event_date` is the canonical date for every event type: livestock_guards.py
	keys its age and interval rules on it, and the desk form relabels it per type
	("Service Date", "Movement Date", "Diagnosis Date"). A form that collects only
	the type-specific date therefore passes `date_key` so that date also becomes
	`event_date`. Without it a backdated entry stored the right `service_date` and
	an `event_date` of today, leaving the two out of step and the interval guards
	reading the wrong day.
	"""
	doc = frappe.new_doc("Livestock Event")
	doc.animal = d.get("animal")
	doc.event_type = event_type
	doc.event_date = d.get("event_date") or (d.get(date_key) if date_key else None) or today()
	doc.operator = _employee_or_throw(d.get("operator"))
	doc.remarks = d.get("remarks")
	return doc


@frappe.whitelist()
def create_movement_event(payload):
	def go():
		_guard("Livestock Event")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("new_herd"):
			frappe.throw(_("Select the destination herd."))
		doc = _new_livestock_event(d, "Movement")
		doc.new_herd = d.get("new_herd")
		doc.insert()
		doc.submit()  # herd_movement_processor updates Animal.current_herd + headcounts
		return {"ok": True, "name": doc.name}

	return _run(go, "livestock create_movement_event failed")


@frappe.whitelist()
def create_drying_off_event(payload):
	def go():
		_guard("Livestock Event")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		doc = _new_livestock_event(d, "Drying Off")
		doc.insert()
		doc.submit()
		return {"ok": True, "name": doc.name}

	return _run(go, "livestock create_drying_off_event failed")


def _calf_row(calf, outcome):
	"""Normalise one incoming calf dict for record_calf_births."""
	tag = (calf.get("name") or "").strip().upper()
	stillborn = outcome != "Live Birth" or not tag or tag == "STILLBORN"
	return {
		"tag": tag,
		"sex": calf.get("sex"),
		"burn_name": tag,
		"birth_weight": calf.get("birth_weight"),
		"is_stillborn": 1 if stillborn else 0,
		"herd": calf.get("herd"),
	}


@frappe.whitelist()
def record_birth(payload):
	"""Record a calving: a Calving Livestock Event + (for live births) one Animal
	record and a Birth event per calf. Ports the "Record Livestock Birth" Server
	Script into a permission-checked whitelist call. No Stock Entry involved."""

	def go():
		_guard("Livestock Event")
		_guard("Animal")
		d = _ok(payload)
		dam_name = d.get("dam") or d.get("animal")
		if not dam_name:
			frappe.throw(_("Select the dam."))
		operator = _employee_or_throw(d.get("operator"))
		event_date = d.get("event_date") or today()
		outcome = d.get("outcome") or "Live Birth"
		related_pregnancy = d.get("related_pregnancy") or ""
		remarks = d.get("remarks") or ""
		calves = d.get("calves") or []
		if not isinstance(calves, list) or not calves:
			frappe.throw(_("Add at least one calf."))

		dam = frappe.get_doc("Animal", dam_name)

		sire = ""
		if related_pregnancy:
			try:
				preg = frappe.get_doc("Livestock Event", related_pregnancy)
				if preg.related_service:
					svc = frappe.get_doc("Livestock Event", preg.related_service)
					sire = svc.sire or ""
			except Exception:
				pass

		calving = frappe.new_doc("Livestock Event")
		calving.animal = dam_name
		calving.event_type = "Calving"
		calving.event_date = event_date
		calving.current_herd = dam.current_herd or ""
		calving.custom_calving_outcome = outcome
		calving.custom_no_of_calves = len(calves)
		calving.sire = sire
		calving.operator = operator
		calving.remarks = remarks
		if len(calves) == 1 and calves[0].get("sex"):
			calving.custom_calf_sex = calves[0].get("sex")
		if related_pregnancy:
			calving.custom_related_pregnancy = related_pregnancy
		calving.insert()
		calving.submit()

		# One calf-creation path: record_calf_births owns the per-calf loop and lets
		# the Livestock Event controller create each Animal. A second copy of this
		# loop here is what would make a form-booked birth create the calf twice.
		#
		# Gated on outcome, matching the pre-Task-9 behaviour exactly: a Still
		# Birth creates only the Calving, with no Birth events at all. Abortion
		# used to reach this same gate as a custom_calving_outcome value; Task 10
		# removed it from that Select entirely (pregnancy loss is now its own
		# Abortion event type — see LivestockEvent.close_pregnancy_after_abortion),
		# so calving.insert() above now rejects outcome="Abortion" itself, before
		# this gate is even reached.
		created = []
		if outcome == "Live Birth":
			created = record_calf_births(
				{
					"calving": calving.name,
					"calves": [_calf_row(c, outcome) for c in calves],
				}
			)["created"]

		return {
			"ok": True,
			"name": calving.name,
			"outcome": outcome,
			"num_calves": len(calves),
			"calves": created,
		}

	return _run(go, "livestock record_birth failed")


# ===========================================================================
# BREEDING  (Service/Insemination · Pregnancy Diagnosis)  — NO Stock Entry
# ===========================================================================


@frappe.whitelist()
def breeding_options():
	def go():
		labels = _herd_label_map()
		animals = _active_animals()
		sires = sorted(
			{
				r.sire
				for r in frappe.get_all(
					"Livestock Event",
					filters=[["sire", "is", "set"]],
					fields=["sire"],
					limit_page_length=500,
				)
				if r.sire
			}
		)
		return {
			"ok": True,
			"animals": _animal_choices(animals, labels),
			"service_types": _select_options("Livestock Event", "service_type") or ["A.I.", "Natural"],
			"diagnosis_results": _select_options("Livestock Event", "diagnosis_result")
			or ["Confirmed", "Not Pregnant", "Aborted"],
			"sires": sires,
			"employee": _current_employee(),
		}

	return _run(go, "livestock breeding_options failed")


@frappe.whitelist()
def breeding_lists():
	"""Supporting worklists: pending pregnancy checks and animals ready to serve."""

	def go():
		labels = _herd_label_map()
		# Pregnancy checks due: submitted Service events still pending, whose
		# 35-day check window has arrived.
		due = frappe.db.sql(
			"""SELECT name, animal, current_herd, service_date, pregnancy_check_due_date
			   FROM `tabLivestock Event`
			   WHERE event_type = 'Service' AND docstatus = 1
			     AND pregnancy_confirmation_status = 'Pending'
			     AND IFNULL(pregnancy_check_due_date, service_date) <= %s
			   ORDER BY pregnancy_check_due_date ASC LIMIT 200""",
			(today(),),
			as_dict=True,
		)
		# Ready for service: active, not currently confirmed-pregnant, no pending
		# service, and past the post-partum window (ready_for_service_date on the
		# last calving, else nothing pending).
		ready = frappe.db.sql(
			"""SELECT a.name, a.tag_number, a.burn_name, a.current_herd, a.repro_status
			   FROM `tabAnimal` a
			   WHERE IFNULL(a.status,'') NOT IN ('Dead','Deceased','Sold','Culled','Disposed')
			     AND NOT EXISTS (
			       SELECT 1 FROM `tabLivestock Event` s
			       WHERE s.animal = a.name AND s.event_type='Service' AND s.docstatus=1
			         AND s.pregnancy_confirmation_status IN ('Pending','Confirmed')
			         AND NOT EXISTS (
			           SELECT 1 FROM `tabLivestock Event` c
			           WHERE c.animal=s.animal AND c.event_type='Calving'
			             AND c.custom_related_pregnancy=s.name AND c.docstatus=1))
			     AND EXISTS (
			       SELECT 1 FROM `tabLivestock Event` cal
			       WHERE cal.animal=a.name AND cal.event_type='Calving' AND cal.docstatus=1
			         AND IFNULL(cal.ready_for_service_date, cal.event_date) <= %s)
			   ORDER BY a.tag_number ASC LIMIT 200""",
			(today(),),
			as_dict=True,
		)
		return {
			"ok": True,
			"pregnancy_checks": [
				{
					"service": r.name,
					"animal": r.animal,
					"herd_label": labels.get(r.current_herd or "", r.current_herd or ""),
					"service_date": str(r.service_date) if r.service_date else "",
					"due": str(r.pregnancy_check_due_date) if r.pregnancy_check_due_date else "",
				}
				for r in due
			],
			"ready_for_service": [
				{
					"animal": r.name,
					"label": _animal_label(r),
					"herd_label": labels.get(r.current_herd or "", r.current_herd or ""),
				}
				for r in ready
			],
		}

	return _run(go, "livestock breeding_lists failed")


@frappe.whitelist()
def create_service_event(payload):
	"""Record a Service / insemination. Creates an Livestock Event ONLY — no Stock
	Entry, no semen-straw inventory movement (see module invariant). The
	"VALIDATION FOR SERVICE EVENTS" Server Script enforces the breeding rules
	and stamps the expected-calving / check-due / next-heat dates."""

	def go():
		_guard("Livestock Event")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		doc = _new_livestock_event(d, "Service", date_key="service_date")
		doc.service_type = d.get("service_type")
		doc.service_date = d.get("service_date") or today()
		doc.sire = d.get("sire")
		doc.insert()
		doc.submit()
		# Invariant check: a Service event must never spawn a Stock Entry.
		assert not frappe.db.exists(
			"Stock Entry", {"remarks": ["like", "%" + doc.name + "%"]}
		), "Service event unexpectedly created a Stock Entry"
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"expected_calving_date": str(doc.expected_calving_date or ""),
			"pregnancy_check_due_date": str(doc.pregnancy_check_due_date or ""),
		}

	return _run(go, "livestock create_service_event failed")


@frappe.whitelist()
def create_pregnancy_diagnosis(payload):
	"""Record a Pregnancy Diagnosis (Livestock Event only). The Server Script
	auto-links the related service when omitted and validates timing."""

	def go():
		_guard("Livestock Event")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("diagnosis_result"):
			frappe.throw(_("Select a diagnosis result."))
		doc = _new_livestock_event(d, "Pregnancy Diagnosis", date_key="diagnosis_date")
		doc.diagnosis_date = d.get("diagnosis_date") or today()
		doc.diagnosis_result = d.get("diagnosis_result")
		doc.diagnosis_remarks = d.get("diagnosis_remarks")
		if d.get("related_service"):
			doc.related_service = d.get("related_service")
		doc.insert()
		doc.submit()
		return {"ok": True, "name": doc.name, "result": doc.diagnosis_result}

	return _run(go, "livestock create_pregnancy_diagnosis failed")


# ===========================================================================
# PARLOUR  (Milking Parlour CFU checksheet)
# ===========================================================================


@frappe.whitelist()
def parlour_options():
	def go():
		assets = frappe.get_all(
			"Asset",
			filters=[["docstatus", "<", 2]],
			fields=["name", "asset_name", "asset_category", "location"],
			order_by="asset_name asc",
			limit_page_length=500,
		)
		return {
			"ok": True,
			"assets": [
				{
					"name": a.name,
					"label": a.asset_name or a.name,
					"category": a.asset_category,
					"location": a.location,
				}
				for a in assets
			],
			"equipment": _select_options("Milking Palour Checksheet", "equipment"),
			"frequencies": _select_options("Milking Palour Checksheet", "frequency") or ["Daily"],
			"statuses": _select_options("CFU Inspection Item", "status"),
			"inspector": frappe.session.user,
		}

	return _run(go, "livestock parlour_options failed")


@frappe.whitelist()
def create_parlour_checksheet(payload):
	def go():
		_guard("Milking Palour Checksheet")
		d = _ok(payload)
		if not d.get("asset"):
			frappe.throw(_("Select an asset."))
		items = d.get("items") or []
		items = [r for r in items if (r.get("part_name") or "").strip()]
		if not items:
			frappe.throw(_("Add at least one inspection row."))

		doc = frappe.new_doc("Milking Palour Checksheet")
		doc.asset = d.get("asset")
		doc.equipment = d.get("equipment")
		doc.frequency = d.get("frequency") or "Daily"
		doc.date = d.get("date") or today()
		doc.time = nowtime()
		doc.inspector = d.get("inspector") or frappe.session.user
		for r in items:
			doc.append(
				"inspection_items",
				{
					"equipment": r.get("equipment") or d.get("equipment") or "",
					"part_name": r.get("part_name"),
					"parameter_checked": r.get("parameter_checked") or "-",
					"status": r.get("status") or "Not Checked",
					"notes": r.get("notes"),
				},
			)
		doc.insert()
		doc.submit()
		return {"ok": True, "name": doc.name, "rows": len(items)}

	return _run(go, "livestock create_parlour_checksheet failed")


# ===========================================================================
# MULTIPLE BIRTHS  (twins/triplets — one Calving, N Birth events)
# ===========================================================================


@frappe.whitelist()
def record_calf_births(payload):
	"""Create one Birth event per calf for an existing Calving event.

	A dam bearing triplets gets one Calving event and three Birth events. Stillborn
	rows are recorded as Birth events that create no Animal, so the calving's count
	stays honest without inflating herd numbers.
	"""

	def go():
		_guard("Livestock Event")
		_guard("Animal")
		d = _ok(payload)
		calving_name = d.get("calving")
		if not calving_name:
			frappe.throw(_("Select the calving event."))
		calves = d.get("calves") or []
		if not isinstance(calves, list) or not calves:
			frappe.throw(_("Add at least one calf."))

		calving = frappe.get_doc("Livestock Event", calving_name)
		if calving.event_type != "Calving":
			frappe.throw(_("{0} is not a Calving event.").format(calving_name))

		dam_name = calving.animal
		dam = frappe.get_doc("Animal", dam_name)
		created = []

		# Suppress the per-Birth mismatch warning for the duration of this loop:
		# each Birth's own on_submit recounts against the calving's FULL expected
		# total, so without this a 3-calf batch would warn "expects 3, got 1"
		# after the first calf and "expects 3, got 2" after the second — false
		# alarms on a batch that is about to complete correctly. births_recorded
		# itself is still refreshed on every single Birth submit regardless (see
		# LivestockEvent.refresh_calving_birth_count); only the message is held
		# back here, evaluated once, after the whole batch, against the final
		# count. The finally ensures an exception mid-loop can't leave the flag
		# set for the rest of the request.
		frappe.flags.suppress_calving_mismatch_warning = True
		try:
			for calf in calves:
				stillborn = bool(calf.get("is_stillborn"))
				birth = frappe.new_doc("Livestock Event")
				birth.event_type = "Birth"
				birth.event_date = calving.event_date
				birth.operator = calving.operator
				birth.dam = dam_name
				birth.related_calving = calving.name
				birth.sire = calving.sire
				birth.is_stillborn = 1 if stillborn else 0

				if stillborn:
					birth.remarks = f"Stillborn. Dam: {dam.tag_number or dam.burn_name}"
				else:
					birth.calf_tag_number = (calf.get("tag") or "").strip().upper()
					birth.calf_sex = calf.get("sex") if calf.get("sex") in ("Female", "Male") else "Female"
					birth.calf_burn_name = calf.get("burn_name") or birth.calf_tag_number
					birth.calf_birth_weight_kg = flt(calf.get("birth_weight"))
					# An empty/omitted herd must still fall back to resolve_calf_herd() —
					# create_calf_if_needed() treats a falsy herd the same as "not given".
					birth.calf_herd = calf.get("herd") or ""
					birth.remarks = f"Dam: {dam.tag_number or dam.burn_name}"

				birth.insert()
				birth.submit()
				if not stillborn:
					created.append(
						{"animal": birth.animal, "tag": birth.calf_tag_number, "sex": birth.calf_sex}
					)
		finally:
			frappe.flags.suppress_calving_mismatch_warning = False

		# One evaluation for the whole batch, against the final, settled count —
		# not one per calf (see the comment above the loop).
		warn_on_calving_mismatch(calving.name)

		calving.reload()
		return {"ok": True, "created": created, "births_recorded": calving.births_recorded}

	return _run(go, "livestock record_calf_births failed")


# ===========================================================================
# ABORTION
# ===========================================================================


@frappe.whitelist()
def create_abortion_event(payload):
	"""Record an Abortion as a first-class Livestock Event.

	`abortion_cause` is enforced by LivestockEvent.validate() rather than by a
	reqd flag on the field (mandatory_depends_on is browser-only in Frappe 16), so
	it is checked here too — otherwise the failure surfaces as a validation throw
	from deep in the controller instead of a clean message on the form.

	The pregnancy link is deliberately not required: the controller auto-links the
	animal's open Confirmed pregnancy when `custom_related_pregnancy` is blank, and
	an abortion with no pregnancy on file is legitimate data rather than an error.
	"""

	def go():
		_guard("Livestock Event")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("abortion_cause"):
			frappe.throw(_("Select the cause of abortion."))
		doc = _new_livestock_event(d, "Abortion")
		doc.abortion_cause = d.get("abortion_cause")
		doc.abortion_notes = d.get("abortion_notes")
		if d.get("related_pregnancy"):
			doc.custom_related_pregnancy = d.get("related_pregnancy")
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"related_pregnancy": doc.custom_related_pregnancy or "",
			"ready_for_service_date": str(doc.ready_for_service_date or ""),
		}

	return _run(go, "livestock create_abortion_event failed")


# ===========================================================================
# DISPOSAL  (sold / died / culled)
# ===========================================================================


@frappe.whitelist()
def disposal_options():
	def go():
		labels = _herd_label_map()
		return {
			"ok": True,
			"animals": _animal_choices(_active_animals(), labels),
			"disposal_types": _select_options("Livestock Disposal", "disposal_type"),
			"customers": [
				c.name
				for c in frappe.get_all(
					"Customer", fields=["name"], order_by="name asc", limit_page_length=500
				)
			],
			"company": _default_company(),
		}

	return _run(go, "livestock disposal_options failed")


@frappe.whitelist()
def record_disposal(payload):
	"""Retire an animal by creating and submitting a Livestock Disposal.

	All the consequences live in LivestockDisposal.on_submit(): it posts the asset
	sale or scrap through api/assets.py and calls retire_animal(), which sets the
	final status, sets `disabled`, and recomputes the herd headcount. This endpoint
	deliberately adds none of that itself — one submit is the whole flow.
	"""

	def go():
		_guard("Livestock Disposal")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("disposal_type"):
			frappe.throw(_("Select how the animal left the herd."))
		doc = frappe.new_doc("Livestock Disposal")
		doc.animal = d.get("animal")
		doc.disposal_date = d.get("disposal_date") or today()
		doc.disposal_type = d.get("disposal_type")
		doc.sale_price = flt(d.get("sale_price")) or None
		doc.customer = d.get("customer") or None
		doc.buyer_name = d.get("buyer_name")
		doc.reason_details = d.get("reason_details")
		doc.witness = d.get("witness")
		doc.insert()
		doc.submit()
		doc.reload()
		status, disabled = frappe.db.get_value("Animal", doc.animal, ["status", "disabled"])
		return {
			"ok": True,
			"name": doc.name,
			"animal_status": status,
			"animal_disabled": int(disabled or 0),
		}

	return _run(go, "livestock record_disposal failed")


# ===========================================================================
# WEIGHT RECORDING
# ===========================================================================


@frappe.whitelist()
def weight_options():
	def go():
		labels = _herd_label_map()
		return {
			"ok": True,
			"animals": _animal_choices(_active_animals(), labels),
			"methods": _select_options("Livestock Weight Record", "method"),
			"employee": _current_employee(),
		}

	return _run(go, "livestock weight_options failed")


@frappe.whitelist()
def create_weight_record(payload):
	"""Record a weighing as a Livestock Weight Record.

	The doctype owns the derived columns (previous weight, daily gain) and the
	minimum-interval guard, so this endpoint only carries the measurement across.
	"""

	def go():
		_guard("Livestock Weight Record")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		weight = flt(d.get("weight_kg"))
		if weight <= 0:
			frappe.throw(_("Weight must be greater than zero."))
		doc = frappe.new_doc("Livestock Weight Record")
		doc.animal = d.get("animal")
		doc.company = _company_or_throw(d.get("company"))
		doc.weight_date = d.get("weight_date") or today()
		doc.measured_by = d.get("measured_by") or _current_employee()
		doc.method = d.get("method") or None
		doc.weight_kg = weight
		doc.bcs = flt(d.get("bcs")) or None
		doc.heart_girth_cm = flt(d.get("heart_girth_cm")) or None
		doc.remarks = d.get("remarks")
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"weight_kg": doc.weight_kg,
			"daily_gain_kg": doc.daily_gain_kg,
			"previous_weight_kg": doc.previous_weight_kg,
		}

	return _run(go, "livestock create_weight_record failed")


# ===========================================================================
# HEALTH  (Check Up = Livestock Diagnosis, Health Case = Livestock Health Case)
# ===========================================================================


@frappe.whitelist()
def health_options():
	def go():
		labels = _herd_label_map()
		return {
			"ok": True,
			"animals": _animal_choices(_active_animals(), labels),
			"diseases": [
				r.name
				for r in frappe.get_all(
					"Livestock Disease", fields=["name"], order_by="name asc", limit_page_length=500
				)
			],
			"abortion_causes": _select_options("Livestock Event", "abortion_cause"),
			"appearances": _select_options("Livestock Diagnosis", "appearance"),
			"hydrations": _select_options("Livestock Diagnosis", "hydration"),
			"actions": _select_options("Livestock Diagnosis", "action_taken"),
			"case_statuses": _select_options("Livestock Health Case", "case_status"),
			"severities": _select_options("Livestock Health Case", "severity"),
			"employee": _current_employee(),
			"company": _default_company(),
		}

	return _run(go, "livestock health_options failed")


@frappe.whitelist()
def create_check_up(payload):
	"""Record a routine check-up as a Livestock Diagnosis.

	LivestockDiagnosis.on_submit() calls sync_event_for(self, "Check Up"), so the
	animal's timeline event is created by the doctype — not here.
	"""

	def go():
		_guard("Livestock Diagnosis")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("action_taken"):
			frappe.throw(_("Select the action taken."))
		doc = frappe.new_doc("Livestock Diagnosis")
		doc.animal = d.get("animal")
		doc.company = _company_or_throw(d.get("company"))
		doc.diagnosis_date = d.get("diagnosis_date") or today()
		doc.operator = _employee_or_throw(d.get("operator"))
		doc.reason_for_check = d.get("reason_for_check")
		doc.appearance = d.get("appearance") or None
		doc.hydration = d.get("hydration") or None
		doc.temperature_c = flt(d.get("temperature_c")) or None
		doc.respiration_rate = int(flt(d.get("respiration_rate"))) or None
		doc.heart_rate = int(flt(d.get("heart_rate"))) or None
		doc.bcs = flt(d.get("bcs")) or None
		doc.lameness_score = int(flt(d.get("lameness_score"))) or None
		doc.suggested_disease = d.get("suggested_disease") or None
		doc.differential_notes = d.get("differential_notes")
		doc.action_taken = d.get("action_taken")
		doc.action_notes = d.get("action_notes")
		doc.follow_up_date = d.get("follow_up_date") or None
		doc.insert()
		doc.submit()
		doc.reload()
		return {"ok": True, "name": doc.name, "action_taken": doc.action_taken}

	return _run(go, "livestock create_check_up failed")


@frappe.whitelist()
def create_health_case(payload):
	"""Open a Livestock Health Case.

	LivestockHealthCase.on_submit() calls sync_event_for(self, "Health Case"), so
	the timeline event is the doctype's job. Treatments are added on the case
	itself afterwards — this endpoint opens the case, it does not close it.
	"""

	def go():
		_guard("Livestock Health Case")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("presenting_symptoms"):
			frappe.throw(_("Describe the presenting symptoms."))
		doc = frappe.new_doc("Livestock Health Case")
		doc.animal = d.get("animal")
		doc.company = _company_or_throw(d.get("company"))
		doc.opened_date = d.get("opened_date") or today()
		doc.opened_by = d.get("opened_by") or _current_employee()
		doc.case_status = d.get("case_status") or "Open"
		doc.presenting_symptoms = d.get("presenting_symptoms")
		doc.body_systems = d.get("body_systems")
		doc.provisional_diagnosis = d.get("provisional_diagnosis") or None
		doc.severity = d.get("severity") or None
		doc.vet_called = 1 if d.get("vet_called") else 0
		doc.vet_name = d.get("vet_name")
		doc.insert()
		doc.submit()
		doc.reload()
		return {"ok": True, "name": doc.name, "case_status": doc.case_status}

	return _run(go, "livestock create_health_case failed")
