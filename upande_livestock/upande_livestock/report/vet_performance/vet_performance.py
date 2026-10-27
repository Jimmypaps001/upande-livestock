# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""How each vet's work is going, for the period asked.

One row per Livestock Vet. Each figure counts only what is recorded against the
vet, so a vet whose work was never entered under their name shows low: this
measures the records, and is only as good as how consistently `vet` is filled.

* Cases opened: submitted health cases opened in the period.
* Check-ups: submitted check-ups (Livestock Diagnosis) in the period.
* Treatments: treatment rows dated in the period, on the vet's cases.
* Health events: husbandry and other vet events (vaccination, deworming, hoof
  trimming, dehorning, pregnancy diagnosis) in the period. The
  timeline events mirrored from cases and check-ups are not counted again.
* Recovered / Chronic / Died / Culled: the vet's cases CLOSED in the period, by
  outcome. Open: the vet's cases still open at the end of the period.
* Avg days to close: opened to closed, over the cases closed in the period.
* Re-treated in 30 days: of those closed cases, how many had a new case opened
  for the same animal within 30 days of closing.
* Drug cost: the cost recorded on the vet's case treatments in the period, plus
  the outgoing value of the stock entries behind their events and check-ups
  (one entry is counted once however many animals it served).
* Vet fees posted: Journal Entries posted for the vet's fees. A fee that could
  not be posted (no supplier / expense account) stays on the event's remarks
  and is not in this figure.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, today

from upande_livestock.serverscripts.common.events import VET_EVENT_TYPES

OUTCOMES = ("Recovered", "Chronic", "Died", "Culled")
WINDOW = 30


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start = getdate(filters.from_date or add_days(today(), -365))
	end = getdate(filters.to_date or today())
	if start > end:
		start, end = end, start
	return columns(), data(filters, start, end)


def columns():
	def col(fieldname, label, fieldtype="Int", width=110, **kw):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width, **kw}

	return [
		col("vet", "Vet", "Link", 110, options="Livestock Vet"),
		col("vet_name", "Name", "Data", 160),
		col("vet_type", "Type", "Data", 80),
		col("cases_opened", "Cases Opened"),
		col("check_ups", "Check-ups"),
		col("treatments", "Treatments"),
		col("health_events", "Health Events"),
		col("recovered", "Recovered"),
		col("chronic", "Chronic"),
		col("died", "Died"),
		col("culled", "Culled"),
		col("still_open", "Open Now"),
		col("avg_days_to_close", "Avg Days to Close", "Float", 120, precision=1),
		col("retreated_30d", "Re-treated in 30 Days", "Int", 130),
		col("drug_cost", "Drug Cost", "Currency", 110),
		col("vet_fees", "Vet Fees Posted", "Currency", 120),
	]


def _animal_filter(company):
	"""The animals of `company`, for records that carry no company of their own."""
	if not company:
		return None
	return frappe.get_all("Animal", filters={"company": company}, pluck="name", limit=1000000)


def data(filters, start, end):
	vet_filter = {"name": filters.vet} if filters.vet else {}
	vets = frappe.get_all(
		"Livestock Vet", filters=vet_filter, fields=["name", "vet_name", "vet_type", "enabled", "supplier"],
		order_by="vet_name asc", limit=1000000,
	)
	rows = {
		v.name: frappe._dict(
			vet=v.name, vet_name=v.vet_name, vet_type=v.vet_type, _enabled=v.enabled,
			cases_opened=0, check_ups=0, treatments=0, health_events=0,
			recovered=0, chronic=0, died=0, culled=0, still_open=0,
			avg_days_to_close=0.0, retreated_30d=0, drug_cost=0.0, vet_fees=0.0,
			_days=[], _entries=set(),
		)
		for v in vets
	}
	if not rows:
		return []
	names = list(rows)
	company = filters.company
	company_filter = {"company": company} if company else {}

	# Cases opened in the period, and the vet's treatment rows within it.
	for c in frappe.get_all(
		"Livestock Health Case",
		filters={"docstatus": 1, "vet": ["in", names], "opened_date": ["between", [start, end]], **company_filter},
		fields=["vet"], limit=1000000,
	):
		rows[c.vet].cases_opened += 1

	for t in frappe.db.sql(
		"""SELECT c.vet, t.cost FROM `tabLivestock Health Treatment` t
		   JOIN `tabLivestock Health Case` c ON c.name = t.parent
		   WHERE t.parenttype = 'Livestock Health Case' AND c.docstatus = 1
		     AND c.vet IN %(vets)s AND t.treatment_date BETWEEN %(start)s AND %(end)s
		     {company}""".format(company="AND c.company = %(company)s" if company else ""),
		{"vets": names, "start": start, "end": end, "company": company}, as_dict=True,
	):
		rows[t.vet].treatments += 1
		rows[t.vet].drug_cost += flt(t.cost)

	# Cases closed in the period: outcomes and time to close.
	closed = frappe.get_all(
		"Livestock Health Case",
		filters={"docstatus": 1, "vet": ["in", names], "closed_date": ["between", [start, end]],
		         "case_status": ["in", list(OUTCOMES)], **company_filter},
		fields=["name", "vet", "animal", "case_status", "opened_date", "closed_date"], limit=1000000,
	)
	for c in closed:
		r = rows[c.vet]
		r[c.case_status.lower()] += 1
		if c.opened_date and c.closed_date:
			r._days.append(date_diff(c.closed_date, c.opened_date))
		if _retreated(c):
			r.retreated_30d += 1

	for c in frappe.get_all(
		"Livestock Health Case",
		filters={"docstatus": 1, "vet": ["in", names], "opened_date": ["<=", end],
		         "case_status": ["in", ["Open", "Under Treatment"]], **company_filter},
		fields=["vet"], limit=1000000,
	):
		rows[c.vet].still_open += 1

	# Check-ups.
	for d in frappe.get_all(
		"Livestock Diagnosis",
		filters={"docstatus": 1, "vet": ["in", names], "diagnosis_date": ["between", [start, end]], **company_filter},
		fields=["vet", "stock_entry"], limit=1000000,
	):
		rows[d.vet].check_ups += 1
		if d.stock_entry:
			rows[d.vet]._entries.add(d.stock_entry)

	# Health events recorded directly (not the timeline mirrors of cases/check-ups).
	event_filters = {
		"docstatus": 1, "vet": ["in", names], "event_date": ["between", [start, end]],
		"event_type": ["in", list(VET_EVENT_TYPES)], "reference_doctype": ["is", "not set"],
	}
	animals = _animal_filter(company)
	if animals is not None:
		event_filters["animal"] = ["in", animals or ["__none__"]]
	for e in frappe.get_all(
		"Livestock Event", filters=event_filters, fields=["vet", "stock_entry"], limit=1000000
	):
		rows[e.vet].health_events += 1
		if e.stock_entry:
			rows[e.vet]._entries.add(e.stock_entry)

	# Stock behind events and check-ups, each entry once.
	for r in rows.values():
		if r._entries:
			r.drug_cost += sum(
				flt(v) for v in frappe.get_all(
					"Stock Entry", filters={"name": ["in", list(r._entries)], "docstatus": 1},
					pluck="total_outgoing_value", limit=1000000,
				)
			)

	# Fees posted as Journal Entries (see serverscripts/common/vet_fee).
	je_filters = {"docstatus": 1, "title": ["in", [f"Vet fee: {n}" for n in names]],
	              "posting_date": ["between", [start, end]], **company_filter}
	for je in frappe.get_all("Journal Entry", filters=je_filters, fields=["title", "total_debit"], limit=1000000):
		vet = je.title[len("Vet fee: "):]
		if vet in rows:
			rows[vet].vet_fees += flt(je.total_debit)

	out = []
	for r in rows.values():
		r.avg_days_to_close = round(sum(r._days) / len(r._days), 1) if r._days else 0.0
		active = (r.cases_opened or r.check_ups or r.treatments or r.health_events or r.recovered
		          or r.chronic or r.died or r.culled or r.still_open or r.vet_fees)
		if r._enabled or active:
			out.append({k: v for k, v in r.items() if not k.startswith("_")})
	return out


def _retreated(case):
	"""Whether the same animal got a new case within 30 days of this one closing."""
	return bool(
		frappe.db.exists(
			"Livestock Health Case",
			{
				"docstatus": 1, "animal": case.animal, "name": ["!=", case.name],
				"opened_date": ["between", [case.closed_date, add_days(case.closed_date, WINDOW)]],
			},
		)
	)
