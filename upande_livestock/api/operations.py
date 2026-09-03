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

STOCK-CONSUMING FLOWS:
  Every livestock flow that consumes something now posts a Stock Entry. Feed
  (feeding.py) and milking (Milk Recording) always did; vaccination, deworming,
  treatment and service post theirs through livestock_stock.try_issue_items, fired
  from the owning controller's on_submit rather than from here.

  This module previously carried the opposite rule — an "INSEMINATION INVARIANT"
  stating that no breeding path may ever create a Stock Entry, enforced by an
  assert in create_service_event. That was an early simplification: an A.I. does
  consume a semen straw, the DAIRY item group already stocks them, and the farm
  needs that movement recorded. The rule and its assert were removed deliberately.
  Pregnancy diagnosis still creates no Stock Entry — it consumes nothing.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, nowtime, today

from upande_livestock import livestock_stock
from upande_livestock.api import feeding
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.upande_livestock.doctype.livestock_event.livestock_event import (
	warn_on_calving_mismatch,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

# `guard`, `as_dict` and `run` moved to serverscripts/common/envelope.py, the
# spine every migrated endpoint imports from directly. These aliases keep the
# 34 call sites below working untouched until each domain migrates in turn;
# they are removed per-domain in later tasks, not all at once here.
_guard, _ok, _run = guard, as_dict, run


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


def _stock_items(kind, warehouse=None):
	"""Items a livestock form can issue, restricted to what is actually in stock.

	`kind` is "drug" or "semen". Offering the whole 595-item DRUGS group would be
	unusable and would mostly name things the store cannot supply, so this returns
	only items with a positive balance, plus their on-hand quantity so the form can
	show it. Stock items are non-disabled and stocked (is_stock_item).

	`warehouse` scopes the balance to the store the issue will actually draw from.
	Summing across every warehouse — which this used to do — offered drugs the
	drug store did not have, because 33 units sat in a packaging store on the
	other side of the farm. The label then promised stock the issue could not
	find, and the issue failed.
	"""
	group = "DRUGS" if kind == "drug" else "DAIRY"
	name_filter = (
		"" if kind == "drug" else "AND LOWER(CONCAT(i.name, ' ', IFNULL(i.item_name, ''))) LIKE '%%semen%%'"
	)
	conditions, params = [], [group]
	if warehouse:
		conditions.append("AND b.warehouse = %s")
		params.append(warehouse)
	rows = frappe.db.sql(
		f"""SELECT i.name, i.item_name, i.stock_uom, SUM(b.actual_qty) AS qty
		    FROM `tabItem` i
		    JOIN `tabBin` b ON b.item_code = i.name
		    WHERE i.item_group = %s
		      AND IFNULL(i.disabled, 0) = 0
		      AND IFNULL(i.is_stock_item, 1) = 1
		      {" ".join(conditions)}
		      {name_filter}
		    GROUP BY i.name
		    HAVING qty > 0
		    ORDER BY i.item_name ASC
		    LIMIT 500""",
		params,
		as_dict=True,
	)
	return [
		{
			"value": r.name,
			"label": f"{r.item_name or r.name}  ·  {flt(r.qty):g} {r.stock_uom or ''} in store".strip(),
			"item_name": r.item_name or r.name,
			"qty": flt(r.qty),
			"uom": r.stock_uom,
		}
		for r in rows
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
def feeding_program(herd):
	"""Both sections of the herd feeding programme — the TMR requirement priced
	against the stores, plus a whole-batch plan per concentrate it draws on."""

	def go():
		info = feeding.get_herd_feeding_program(herd)
		info["ok"] = True
		return info

	return _run(go, "livestock feeding_program failed")


@frappe.whitelist()
def manufacture_feed(herd, allow_shortage=False, employee=None):
	def go():
		_guard("Work Order")
		_guard("Stock Entry")
		res = feeding.manufacture_herd_feed(herd, allow_shortage=allow_shortage, employee=employee)
		res["ok"] = True
		return res

	return _run(go, "livestock manufacture_feed failed")


@frappe.whitelist()
def manufacture_concentrate(item_code, qty=None, bom_no=None, allow_shortage=False):
	def go():
		_guard("Work Order")
		_guard("Stock Entry")
		res = feeding.manufacture_concentrate(
			item_code, qty=qty, bom_no=bom_no, allow_shortage=allow_shortage
		)
		res["ok"] = True
		return res

	return _run(go, "livestock manufacture_concentrate failed")


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
	"""Herds that are actually in milk.

	Offering every herd let a milking be recorded against calves and dry cows.
	The lactation groups are read off Herd Movement settings rather than marked
	by hand, because a hand-marked list drifts the first time a herd is renamed
	or added.
	"""

	def go():
		from upande_livestock import herd_movement

		allowed = herd_movement.milking_herds()
		filters = {"name": ["in", allowed]} if allowed else None
		herds = frappe.get_all(
			"Herds", filters=filters, fields=["name", "herd_name", "cost_center"],
			order_by="herd_name asc",
		)
		return {
			"ok": True,
			"herds": [{"name": h.name, "label": h.herd_name or h.name} for h in herds],
			"restricted_to": allowed,
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
		doc.milking_time = d.get("milking_time") or nowtime()
		doc.recording_date = d.get("recording_date") or today()
		doc.cows_milked = int(flt(d.get("cows_milked")))
		doc.operator = d.get("operator") or _current_employee()
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
		doc.bulk_scc = flt(d.get("bulk_scc")) or None
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
def eligibility():
	"""Everything a client needs to offer only what an animal is eligible for.

	One call rather than several, because a mobile client on a farm network
	should not need four round trips to work out whether it may show a cow in a
	milking form. All of it is DERIVED from Herd Movement settings — a client
	that filters on its own hand-marked flags drifts the moment a herd is
	renamed or added, which is what the app was doing with custom_is_milking.
	"""

	def go():
		from upande_livestock import herd_movement

		ladder = herd_movement.growth_ladder()
		return {
			"ok": True,
			"milking_herds": herd_movement.milking_herds(),
			"service_herds": herd_movement.service_herds(),
			"service_wait_days": herd_movement.service_wait_days(),
			"growth_ladder": ladder,
			# next_herd per rung, so a client can propose a destination without
			# re-deriving the order and getting it subtly wrong.
			"next_herd": {
				r["herd"]: herd_movement.next_growth_herd(r["herd"])
				for r in ladder
			},
			"calf_herds": {
				"female": herd_movement.calf_herd("Female"),
				"male": herd_movement.calf_herd("Male"),
			},
			"diagnosable": [r["animal"] for r in herd_movement.diagnosable_animals()],
		}

	return _run(go, "livestock eligibility failed")


@frappe.whitelist()
def movement_suggestions():
	"""What the herd structure says should happen next.

	Read-only. Nothing here moves an animal — it proposes, and a person decides.
	"""

	def go():
		from upande_livestock import herd_movement

		res = herd_movement.suggestions()
		res["ok"] = True
		return res

	return _run(go, "livestock movement_suggestions failed")


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
def create_heat_event(payload):
	"""Record a Heat Detection — an observation, nothing more.

	It consumes no stock and moves no animal, but it is the fact a service is
	timed off, so it needs a home of its own rather than being folded into the
	husbandry endpoint (whose types all carry a vet, a cost or a drug row).
	"""

	def go():
		_guard("Livestock Event")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		doc = _new_livestock_event(d, "Heat Detection")
		doc.insert()
		doc.submit()
		return {"ok": True, "name": doc.name}

	return _run(go, "livestock create_heat_event failed")


@frappe.whitelist()
def create_drying_off_event(payload):
	def go():
		_guard("Livestock Event")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		doc = _new_livestock_event(d, "Drying Off")
		if d.get("new_herd"):
			doc.new_herd = d.get("new_herd")
		# Drying off a cow means sealing her quarters, so Livestock Event Type
		# flags it drug-consuming. The rows were being read off the payload by
		# nothing at all, which left the teat sealant on the shelf while the
		# ledger said the cow was dry.
		for drug in _clean_drug_rows(d.get("drugs"), d.get("source_warehouse") or livestock_stock.drug_warehouse()):
			doc.append("drug_issues", drug)
		doc.insert()
		doc.submit()  # LivestockEvent.on_submit posts the issue as "Animal Treatment"
		doc.reload()
		return {"ok": True, "name": doc.name, "stock_entry": doc.stock_entry or ""}

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
		# record_calf_births reads all four off the row and stamps them on the
		# Birth event, which passes them to the Animal. Leaving them out here is
		# what made a birth booked through record_birth arrive with no breed, no
		# condition at birth and no photo.
		"breed": calf.get("breed"),
		"health_status": calf.get("health_status"),
		"vet_remarks": calf.get("vet_remarks"),
		"photo": calf.get("photo"),
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
		from upande_livestock import herd_movement

		labels = _herd_label_map()
		# Only animals a service can happen to: the top rung of the growth ladder
		# and cows already in milk that are past the post-calving wait. A weaner
		# in the offer list is an invitation to record a service that biology
		# rules out.
		animals = [a for a in _active_animals() if herd_movement.is_servable(a.name)]
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
			"service_herds": herd_movement.service_herds(),
			"service_wait_days": herd_movement.service_wait_days(),
			# Only animals with an open service can be diagnosed — the form's
			# animal list for diagnosis is not the same as the one for service.
			"diagnosis_animals": _animal_choices(
				[a for a in _active_animals()
				 if a.name in {r["animal"] for r in herd_movement.diagnosable_animals()}],
				labels,
			),
			"service_types": _select_options("Livestock Event", "service_type") or ["A.I.", "Natural"],
			"diagnosis_results": _select_options("Livestock Event", "diagnosis_result")
			or ["Confirmed", "Not Pregnant", "Aborted"],
			"sires": sires,
			"semen_items": _stock_items("semen", livestock_stock.semen_warehouse()),
			"default_semen_item": livestock_stock.default_semen_item(),
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
	"""Record a Service / insemination.

	LivestockEvent.validate() enforces the breeding rules and stamps the
	expected-calving / check-due / next-heat dates; its on_submit issues the semen
	straw out of the semen store. The straw item falls back to Livestock Settings
	when the caller does not name one.
	"""

	def go():
		_guard("Livestock Event")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		doc = _new_livestock_event(d, "Service", date_key="service_date")
		doc.service_type = d.get("service_type")
		doc.service_date = d.get("service_date") or today()
		doc.sire = d.get("sire")
		doc.semen_item = d.get("semen_item") or None
		doc.semen_qty = flt(d.get("semen_qty")) or 1
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"expected_calving_date": str(doc.expected_calving_date or ""),
			"pregnancy_check_due_date": str(doc.pregnancy_check_due_date or ""),
			"stock_entry": doc.stock_entry or "",
		}

	return _run(go, "livestock create_service_event failed")


@frappe.whitelist()
def create_pregnancy_diagnosis(payload):
	"""Record a Pregnancy Diagnosis (Livestock Event only). The Server Script
	auto-links the related service when omitted and validates timing."""

	def go():
		from upande_livestock import herd_movement

		_guard("Livestock Event")
		d = _ok(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("diagnosis_result"):
			frappe.throw(_("Select a diagnosis result."))
		# A diagnosis answers a question a service asked. Without an open service
		# there is nothing to diagnose, and a "Confirmed" would invent a pregnancy
		# out of nothing — which then drives calving, herd moves and milk.
		if not d.get("related_service") and not herd_movement.has_open_service(d["animal"]):
			frappe.throw(
				_("{0} has no service awaiting a pregnancy check. Record the service first.").format(
					d["animal"]
				)
			)
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


# ===========================================================================
# MULTIPLE BIRTHS  (twins/triplets — one Calving, N Birth events)
# ===========================================================================


@frappe.whitelist()
def record_calf_births(payload):
	"""Create one Birth event per calf for an existing Calving event.

	A dam bearing triplets gets one Calving event and three Birth events. Stillborn
	rows are recorded as Birth events that create no Animal, so the calving's count
	stays honest without inflating herd numbers — a dam with twins where one lives
	and one dies is two rows with two different outcomes, not an average.

	Each live calf carries its own breed, condition at birth and photo, and is
	routed to a herd by its sex.
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
					# create_calf_if_needed() treats a falsy herd the same as "not given",
					# and that fallback now routes on sex.
					birth.calf_herd = calf.get("herd") or ""
					birth.calf_breed = calf.get("breed") or None
					birth.calf_health_status = calf.get("health_status") or None
					birth.calf_vet_remarks = calf.get("vet_remarks") or None
					birth.calf_photo = calf.get("photo") or None
					birth.remarks = f"Dam: {dam.tag_number or dam.burn_name}"

				birth.insert()
				birth.submit()
				if not stillborn:
					created.append({
						"animal": birth.animal,
						"tag": birth.calf_tag_number,
						"sex": birth.calf_sex,
						"herd": frappe.db.get_value("Animal", birth.animal, "current_herd"),
						"breed": frappe.db.get_value("Animal", birth.animal, "breed"),
						"health_status": birth.calf_health_status,
					})
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
		doc.buyer_contact = d.get("buyer_contact")
		doc.gifted_to = d.get("gifted_to")
		doc.gift_destination = d.get("gift_destination")
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
			# A treatment row is refused outright if its route is not one of
			# these, so the form has to be able to offer them rather than let
			# the operator type "Oral" and lose the whole case.
			"routes": _select_options("Livestock Health Treatment", "route"),
			"responses": _select_options("Livestock Health Treatment", "response_observed"),
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
		# Anything given at the check. LivestockDiagnosis.post_drug_issue posts these
		# out of the drug store on submit, and blocks the check if it cannot.
		for drug in _clean_drug_rows(d.get("drugs"), d.get("source_warehouse") or livestock_stock.drug_warehouse()):
			doc.append("drug_issues", drug)
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"action_taken": doc.action_taken,
			"stock_entry": doc.stock_entry or "",
			"drugs_issued": len(doc.drug_issues or []),
		}

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
		# Treatments given at the point of opening. Each row naming a drug_item is
		# issued out of the drug store by LivestockHealthCase.on_submit; further
		# treatments are added on the case itself later.
		for t in d.get("treatments") or []:
			if not (t.get("drug_item") or t.get("drug_name_text")):
				continue
			doc.append(
				"treatments",
				{
					"treatment_date": t.get("treatment_date") or today(),
					"drug_item": t.get("drug_item") or None,
					"drug_name_text": t.get("drug_name_text"),
					"dosage": t.get("dosage"),
					"qty": flt(t.get("qty")) or 1,
					"route": t.get("route") or None,
					"withdrawal_period_days": int(flt(t.get("withdrawal_period_days"))) or None,
					"administered_by": t.get("administered_by") or _current_employee(),
					"notes": t.get("notes"),
				},
			)
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"case_status": doc.case_status,
			"treatments": len(doc.treatments or []),
			"drug_stock_entry": doc.drug_stock_entry or "",
		}

	return _run(go, "livestock create_health_case failed")


@frappe.whitelist()
def open_health_cases():
	"""Cases still being treated, for the treatment form's case picker."""

	def go():
		rows = frappe.get_all(
			"Livestock Health Case",
			filters={"docstatus": 1, "case_status": ["!=", "Closed"]},
			fields=["name", "animal", "animal_name", "case_status", "opened_date", "provisional_diagnosis"],
			order_by="opened_date desc",
			limit_page_length=200,
		)
		return {
			"ok": True,
			"cases": [
				{
					"value": r.name,
					"label": "{0} · {1}{2}".format(
						r.name,
						r.animal_name or r.animal,
						" · " + r.provisional_diagnosis if r.provisional_diagnosis else "",
					),
					"animal": r.animal,
				}
				for r in rows
			],
			"drug_items": _stock_items("drug", livestock_stock.drug_warehouse()),
			"routes": _select_options("Livestock Health Treatment", "route"),
			"employee": _current_employee(),
		}

	return _run(go, "livestock open_health_cases failed")


@frappe.whitelist()
def add_case_treatment(payload):
	"""Add today's treatment to an open case and issue its drugs.

	Treatments are `allow_on_submit`, and the issue guard lives on the row, so
	this appends to a live case rather than amending it. The drugs go out of the
	store as they are recorded — a case treated for five days posts five issues,
	not one, which is what the store actually saw.
	"""

	def go():
		_guard("Livestock Health Case")
		d = _ok(payload)
		if not d.get("case"):
			frappe.throw(_("Select a case."))
		treatments = [
			t for t in (d.get("treatments") or []) if t.get("drug_item") or t.get("drug_name_text")
		]
		if not treatments:
			frappe.throw(_("Add at least one treatment."))

		doc = frappe.get_doc("Livestock Health Case", d["case"])
		if doc.docstatus != 1:
			frappe.throw(_("Case {0} is not submitted.").format(doc.name))

		before = {t.name for t in doc.treatments or []}
		for t in treatments:
			doc.append(
				"treatments",
				{
					"treatment_date": t.get("treatment_date") or d.get("treatment_date") or today(),
					"drug_item": t.get("drug_item") or None,
					"drug_name_text": t.get("drug_name_text"),
					"dosage": t.get("dosage"),
					"qty": flt(t.get("qty")) or 1,
					"route": t.get("route") or None,
					"withdrawal_period_days": int(flt(t.get("withdrawal_period_days"))) or None,
					"administered_by": t.get("administered_by") or _current_employee(),
					"notes": t.get("notes"),
				},
			)
		doc.flags.ignore_permissions = True
		doc.save()
		doc.reload()
		added = [t for t in doc.treatments or [] if t.name not in before]
		return {
			"ok": True,
			"name": doc.name,
			"animal": doc.animal,
			"added": len(added),
			"treatments": len(doc.treatments or []),
			"stock_entry": (added[0].stock_entry_ref if added else "") or "",
		}

	return _run(go, "livestock add_case_treatment failed")


# ===========================================================================
# HUSBANDRY  (Vaccination, Deworming, Dehorning, Hoof Trimming)
# ===========================================================================

HUSBANDRY_TYPES = ("Vaccination", "Deworming", "Dehorning", "Hoof Trimming")

# Only these two consume drugs out of a store. Dehorning and hoof trimming are
# procedures — they use a tool, not stock — so their forms carry no drug rows.
DRUG_CONSUMING_TYPES = ("Vaccination", "Deworming")


@frappe.whitelist()
def husbandry_options():
	def go():
		labels = _herd_label_map()
		return {
			"ok": True,
			"animals": _animal_choices(_active_animals(), labels),
			"event_types": list(HUSBANDRY_TYPES),
			"drug_consuming_types": list(DRUG_CONSUMING_TYPES),
			"drug_items": _stock_items("drug", livestock_stock.drug_warehouse()),
			"drug_warehouse": livestock_stock.drug_warehouse(),
			"herds": [
				{"name": h.name, "label": h.herd_name or h.name, "heads": int(h.number_of_animals or 0)}
				for h in frappe.get_all(
					"Herds", fields=["name", "herd_name", "number_of_animals"], order_by="herd_name asc"
				)
			],
			"warehouses": [
				w.name
				for w in frappe.get_all(
					"Warehouse",
					filters={"is_group": 0, "disabled": 0},
					fields=["name"],
					order_by="name asc",
					limit_page_length=500,
				)
			],
			"employee": _current_employee(),
		}

	return _run(go, "livestock husbandry_options failed")


@frappe.whitelist()
def drugs_in_store(warehouse=None):
	"""The drug picker for one store, with that store's balances.

	Called when the user changes the store, so the quantities on screen always
	describe the shelf the issue will come off.
	"""

	def go():
		wh = warehouse or livestock_stock.drug_warehouse()
		return {"ok": True, "warehouse": wh, "drug_items": _stock_items("drug", wh)}

	return _run(go, "livestock drugs_in_store failed")


@frappe.whitelist()
def herd_animals(herd):
	"""Active animals in a herd — the target list for a whole-herd round."""

	def go():
		labels = _herd_label_map()
		animals = _animals_in_herd(herd)
		return {"ok": True, "herd": herd, "animals": _animal_choices(animals, labels), "count": len(animals)}

	return _run(go, "livestock herd_animals failed")


@frappe.whitelist()
def create_husbandry_event(payload):
	"""Record a Vaccination / Deworming / Dehorning / Hoof Trimming event.

	For the two drug-consuming types the `drugs` rows become Livestock Drug Issue
	child rows, and LivestockEvent.on_submit posts them as one Material Issue out of
	the drug store. A drug row with no item or a non-positive qty is dropped rather
	than rejected — a half-filled line should not cost the user the whole event.

	The event records even when the issue cannot post; see
	livestock_stock.try_issue_items for why that is the deliberate choice.
	"""

	def go():
		_guard("Livestock Event")
		d = _ok(payload)
		event_type = d.get("event_type")
		if event_type not in HUSBANDRY_TYPES:
			frappe.throw(
				_("{0} is not a husbandry event type. Expected one of: {1}.").format(
					event_type or _("(none)"), ", ".join(HUSBANDRY_TYPES)
				)
			)

		animals = _husbandry_targets(d)
		consumes = _type_consumes_drugs(event_type)
		default_wh = d.get("source_warehouse") or livestock_stock.drug_warehouse()
		drugs = _clean_drug_rows(d.get("drugs"), default_wh) if consumes else []

		# One Material Issue for the whole round, not one per animal. Dosing is
		# entered per animal — 2 ml a cow across 119 cows — so the store sees a
		# single line of 238 ml, which is both what left the shelf and what the
		# storekeeper can reconcile. The events are then stamped with that entry,
		# and LivestockEvent.post_stock_issue's `self.stock_entry` guard stops each
		# one posting again.
		stock_entry = None
		if drugs:
			rows = [
				{
					"item_code": drug["item_code"],
					"qty": drug["qty"] * len(animals),
					"warehouse": drug["source_warehouse"],
					"batch_no": drug.get("batch_no"),
					"uom": drug.get("uom"),
				}
				for drug in drugs
			]
			stock_entry = livestock_stock.issue_items(
				rows,
				remarks="Livestock {0} - {1} animal(s)".format(event_type, len(animals)),
				posting_date=d.get("event_date"),
				employee=d.get("operator"),
				# So the ledger says "Deworming", not "Material Issue".
				what=event_type,
			)

		created = []
		for animal in animals:
			doc = _new_livestock_event(dict(d, animal=animal), event_type)
			for drug in drugs:
				doc.append("drug_issues", dict(drug, stock_entry_ref=stock_entry))
			if stock_entry:
				doc.stock_entry = stock_entry
			doc.insert()
			doc.submit()
			created.append(doc.name)

		return {
			"ok": True,
			"name": created[0] if created else "",
			"names": created,
			"animals": len(created),
			"event_type": event_type,
			"stock_entry": stock_entry or "",
			"drugs_issued": len(drugs),
			"qty_per_animal": sum(drug["qty"] for drug in drugs),
		}

	return _run(go, "livestock create_husbandry_event failed")


def _type_consumes_drugs(event_type):
	"""Read off Livestock Event Type, so the farm can flag a new drug-consuming
	type without a deploy. DRUG_CONSUMING_TYPES is the fallback for a site whose
	event types predate the flag."""
	flagged = frappe.db.get_value("Livestock Event Type", event_type, "consumes_drugs")
	if flagged is None:
		return event_type in DRUG_CONSUMING_TYPES
	return bool(flagged)


def _animals_in_herd(herd):
	"""Animals in a herd that may still receive an event.

	Same rule as _active_animals — retired status or `disabled` excludes an
	animal. `Herds.number_of_animals` is NOT that count: it counts every animal
	whose current_herd points here regardless of status, so dosing off it would
	issue drugs for cows that are dead or sold.
	"""
	return frappe.get_all(
		"Animal",
		filters=[
			["current_herd", "=", herd],
			["status", "not in", _RETIRED_STATUSES],
			["disabled", "=", 0],
		],
		fields=_ANIMAL_FIELDS,
		order_by="tag_number asc",
		limit=5000,
	)


def _husbandry_targets(d):
	"""The animals this event applies to: one, a chosen set, or a whole herd.

	Deworming a herd is one operation to the person doing it and one issue out of
	the store, but it is still a clinical fact about each cow — withdrawal dates
	and next-due dates are per animal. So the round fans out into one event per
	animal, and only the stock side is batched.
	"""
	animals = [a for a in (d.get("animals") or []) if a]
	if not animals and d.get("animal"):
		animals = [d["animal"]]
	if not animals and d.get("herd"):
		animals = [a.name for a in _animals_in_herd(d["herd"])]
		if not animals:
			frappe.throw(_("Herd {0} has no active animals.").format(d["herd"]))
	if not animals:
		frappe.throw(_("Select an animal, a set of animals, or a herd."))
	return animals


def _clean_drug_rows(drugs, default_wh):
	"""Drop half-filled drug lines; quantities here are PER ANIMAL.

	A blank line should not cost the user the whole event, so an incomplete row is
	dropped rather than rejected.
	"""
	rows = []
	for drug in drugs or []:
		if not drug.get("item_code") or flt(drug.get("qty")) <= 0:
			continue
		rows.append(
			{
				"item_code": drug["item_code"],
				"qty": flt(drug["qty"]),
				"source_warehouse": drug.get("source_warehouse") or default_wh,
				"batch_no": drug.get("batch_no"),
				"dosage": drug.get("dosage"),
				"uom": drug.get("uom"),
				"withdrawal_days": int(flt(drug.get("withdrawal_days"))) or None,
				"next_due_date": drug.get("next_due_date") or None,
			}
		)
	return rows
