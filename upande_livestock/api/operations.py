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
	return {
		h.name: (h.herd_name or h.name)
		for h in frappe.get_all("Herds", fields=["name", "herd_name"])
	}


def _animal_label(row):
	return row.get("tag_number") or row.get("burn_name") or row.get("name")


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
		herds = frappe.get_all(
			"Herds", fields=["name", "herd_name", "cost_center"], order_by="herd_name asc"
		)
		return {
			"ok": True,
			"herds": [{"name": h.name, "label": h.herd_name or h.name} for h in herds],
			"sessions": _select_options("Milk Recording", "session"),
			"company": frappe.db.get_single_value("Livestock Settings", "custom_default_company")
			or frappe.defaults.get_user_default("company"),
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
		animals = frappe.get_all(
			"Animal",
			filters=[["status", "not in", ["Dead", "Deceased", "Sold", "Culled", "Disposed"]]],
			fields=["name", "tag_number", "burn_name", "current_herd", "repro_status"],
			order_by="tag_number asc",
			limit_page_length=5000,
		)
		return {
			"ok": True,
			"animals": [
				{
					"name": a.name,
					"label": _animal_label(a),
					"herd": a.current_herd,
					"herd_label": labels.get(a.current_herd or "", a.current_herd or ""),
					"repro": a.repro_status,
				}
				for a in animals
			],
			"herds": [{"name": n, "label": l} for n, l in sorted(labels.items(), key=lambda x: x[1])],
			"calving_outcomes": _select_options("Livestock Event", "custom_calving_outcome")
			or ["Live Birth", "Still Birth", "Abortion"],
			"employee": _current_employee(),
		}

	return _run(go, "livestock event_options failed")


def _new_livestock_event(d, event_type):
	doc = frappe.new_doc("Livestock Event")
	doc.animal = d.get("animal")
	doc.event_type = event_type
	doc.event_date = d.get("event_date") or today()
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

		created = []
		if outcome == "Live Birth":
			for calf in calves:
				calf_id = (calf.get("name") or "").strip().upper()
				if not calf_id or calf_id == "STILLBORN":
					continue
				sex = calf.get("sex") if calf.get("sex") in ("Female", "Male") else "Female"
				weight = flt(calf.get("birth_weight"))
				herd = calf.get("herd") or dam.current_herd or ""
				animal = frappe.new_doc("Animal")
				animal.tag_number = calf_id
				animal.burn_name = calf_id
				animal.sex = sex
				animal.date_of_birth = event_date
				animal.current_herd = herd
				animal.company = dam.company or frappe.db.get_single_value(
					"Livestock Settings", "custom_default_company"
				)
				animal.dam = dam_name
				animal.sire_name = sire
				animal.birth_weight_kg = weight
				animal.origin = "Born on Farm"
				animal.status = "Active"
				animal.repro_status = "Calf"
				if dam.breed:
					animal.breed = dam.breed
				animal.insert()

				birth = frappe.new_doc("Livestock Event")
				birth.animal = animal.name
				birth.event_type = "Birth"
				birth.event_date = event_date
				birth.current_herd = herd
				birth.sire = sire
				birth.operator = operator
				birth.remarks = "Dam: {0}. Birth weight: {1} kg".format(
					dam.tag_number or dam.burn_name, weight
				)
				birth.insert()
				birth.submit()
				created.append({"animal": animal.name, "tag": calf_id, "sex": sex})

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
		animals = frappe.get_all(
			"Animal",
			filters=[["status", "not in", ["Dead", "Deceased", "Sold", "Culled", "Disposed"]]],
			fields=["name", "tag_number", "burn_name", "current_herd", "repro_status"],
			order_by="tag_number asc",
			limit_page_length=5000,
		)
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
			"animals": [
				{
					"name": a.name,
					"label": _animal_label(a),
					"herd_label": labels.get(a.current_herd or "", a.current_herd or ""),
					"repro": a.repro_status,
				}
				for a in animals
			],
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
		doc = _new_livestock_event(d, "Service")
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
		doc = _new_livestock_event(d, "Pregnancy Diagnosis")
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
