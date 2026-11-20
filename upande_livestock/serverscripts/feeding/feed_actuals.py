# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A herd's feed day: the monthly recipe is the plan, what was fed is the actual.

The herd's ration (its BOM) says what a head should eat; the farm rarely feeds
exactly that. Heifers get 300 kg on a day the recipe says 200, because of
appetite. This module keeps the two apart:

* PLAN: each recipe line per head, times the head fed. Never changed from here.
* ACTUAL: what went into the mixer, per component, for the herd and the day.
  Without an amendment it is the plan.

Every day loads from the recipe. An amendment belongs to that herd and that
day alone: it is a record dated that day, so the next day (which has no record)
loads the recipe's plan again, and the recipe itself (the BOM) is never
touched. Only the Ration Editor changes what loads. An item that was not used
at all is removed by setting its actual to 0 (it is left out of what is
manufactured); `reset_day` drops the amendment and puts the day back to the
recipe.

Appetite has no threshold. Each animal shows its variance in kg and percent
against plan; appetite is "below" (variance under 0), "above" (over 0) or
"on_plan" (the variance rounds to 0 at 0.01 kg).

One Livestock Feed Actual record holds a herd's day (unique on date + herd).
Amending changes only that record's actual kilograms. Manufacturing the actuals
mixes and issues THOSE quantities through the feeding engine: the actuals become
a tuned recipe scaled to the weighed total (`_tuned_bom`), so the Work Order and
the Stock Entries consume exactly what was fed. When the store cannot cover it
the mix is kept as a draft dated that day, recording what was used, instead of
failing (`_engine.manufacture_herd_feed(draft_when_short=True)`).

Units: a component's figures are in its recipe unit (kilograms for a feed
line). The `planned_kg` / `actual_kg` names are kept for every row, and only
kilogram rows add into the totals.

Per-animal figures are the herd's total divided by the head fed
(`Herds.number_of_animals`): the farm feeds a pen, so each animal is credited
with an equal share. The daily report
(`daily_feed_report`) reads the same functions.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, today

from upande_livestock.serverscripts.common.idempotency import idempotent
from upande_livestock.serverscripts.common import backdate, event_types
from upande_livestock.serverscripts.common.envelope import guard, guard_read, guard_stock, run
from upande_livestock.serverscripts.common.employee import acting_employee
from upande_livestock.serverscripts.feeding import _engine as feeding
from upande_livestock.serverscripts.feeding import _feed_types as feed_types
from upande_livestock.serverscripts.feeding._units import is_kg

DOCTYPE = "Livestock Feed Actual"

#: The record's links to the Stock Entries of the mix.
STOCK_LINKS = ("transfer_stock_entry", "manufacture_stock_entry", "issue_stock_entry")

#: Rounding of kilograms, matching the doctype's precision.
PRECISION = 3



def appetite(variance_kg):
	""""below" the plan, "above" it, or "on_plan" (0.01 kg rounds to nothing)."""
	v = flt(variance_kg, 2)
	if v < 0:
		return "below"
	if v > 0:
		return "above"
	return "on_plan"


def appetite_totals(rows):
	"""Counts of animals {below_plan, above_plan, on_plan} from rows with an `appetite`."""
	return {
		"below_plan": sum(1 for r in rows if r["appetite"] == "below"),
		"above_plan": sum(1 for r in rows if r["appetite"] == "above"),
		"on_plan": sum(1 for r in rows if r["appetite"] == "on_plan"),
	}


# ---------------------------------------------------------------------------
# reading a herd's day
# ---------------------------------------------------------------------------


def _day_of(date):
	day = getdate(date or today())
	backdate.assert_not_future(str(day), _("Date fed"))
	return day


def _plan(herd):
	"""(bom, heads, lines) of the herd's standing recipe, per head and for the herd.

	Each line: item_code, item_name, uom, per_head, planned (per head x head).
	"""
	_herd_doc, bom, heads = feeding._herd_bom(herd)
	lines = [
		{
			"item_code": r.item_code,
			"item_name": r.item_name or r.item_code,
			"uom": r.uom or r.stock_uom or "",
			"per_head": flt(r.qty),
			"planned": flt(flt(r.qty) * heads, PRECISION),
		}
		for r in bom.items
	]
	return bom, heads, lines


def _record_name(herd, day):
	return frappe.db.get_value(DOCTYPE, {"herd": herd, "date": day}, "name")


def _total_kg(rows, key):
	"""Sum of the kilogram rows only: a gram dose does not add into kilos."""
	return flt(sum(flt(r[key]) for r in rows if is_kg(r["uom"])), PRECISION)


def _issued_on(bom, herd, day):
	"""Feed runs already booked for the herd's ration item on `day` (old route or ours)."""
	from upande_livestock.serverscripts.feeding import feed_day_status

	return feed_day_status._issues_on(bom.item, herd, day)


def herd_day(herd, date=None):
	"""One herd's day: plan and actual per component, as plain data. Read-only.

	From the saved record when there is one (its plan is a snapshot, so a recipe
	changed later does not rewrite a past day); otherwise from the herd's recipe
	with actual = plan.
	"""
	day = _day_of(date)
	herd_doc = frappe.db.get_value("Herds", herd, ["name", "herd_name", "bom"], as_dict=True)
	if not herd_doc:
		frappe.throw(_("Herd {0} was not found.").format(herd))
	name = _record_name(herd, day)
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		heads = int(doc.head_count or 0)
		components = [
			{
				"item_code": r.item_code,
				"item_name": r.item_name or r.item_code,
				"uom": r.uom or "",
				"planned_kg": flt(r.planned_kg),
				"actual_kg": flt(r.actual_kg),
				"removed": flt(r.planned_kg) > 0 and flt(r.actual_kg) <= 0,
			}
			for r in doc.items
		]
		status, bom_name, amended = doc.status, doc.bom, bool(doc.amended)
		record = doc.name
		stock = {
			"work_order": doc.work_order,
			"transfer_stock_entry": doc.transfer_stock_entry,
			"manufacture_stock_entry": doc.manufacture_stock_entry,
			"issue_stock_entry": doc.issue_stock_entry,
			"livestock_event": doc.livestock_event,
		}
		remarks = doc.remarks
	else:
		bom, heads, lines = _plan(herd)
		components = [
			{
				"item_code": ln["item_code"],
				"item_name": ln["item_name"],
				"uom": ln["uom"],
				"planned_kg": ln["planned"],
				"actual_kg": ln["planned"],
				"removed": False,
			}
			for ln in lines
		]
		status, bom_name, amended, record, remarks = "Planned", bom.name, False, None, None
		stock = {}

	planned_kg = _total_kg(components, "planned_kg")
	actual_kg = _total_kg(components, "actual_kg")
	per_head_planned = flt(planned_kg / heads, PRECISION) if heads else 0.0
	per_head_actual = flt(actual_kg / heads, PRECISION) if heads else 0.0
	for c in components:
		c["planned_per_head"] = flt(c["planned_kg"] / heads, 4) if heads else 0.0
		c["actual_per_head"] = flt(c["actual_kg"] / heads, 4) if heads else 0.0
	drafts = _draft_entries(stock)
	return {
		"herd": herd,
		"herd_name": herd_doc.herd_name or herd,
		"date": str(day),
		"record": record,
		"bom": bom_name,
		"head_count": heads,
		"status": status,
		"amended": amended,
		"planned_kg": planned_kg,
		"actual_kg": actual_kg,
		"planned_per_head": per_head_planned,
		"actual_per_head": per_head_actual,
		"variance_kg": flt(actual_kg - planned_kg, PRECISION),
		"components": components,
		"draft_entries": drafts,
		"stock": stock,
		"remarks": remarks,
	}


def _draft_entries(stock):
	"""Names of the day's Stock Entries still waiting as drafts."""
	names = [v for k, v in (stock or {}).items() if k.endswith("stock_entry") and v]
	if not names:
		return []
	return frappe.get_all(
		"Stock Entry", filters={"name": ["in", names], "docstatus": 0}, pluck="name", order_by="name asc"
	)


def day_program(date=None, herd=None):
	"""Every herd that is fed (or just the one), its plan and actual for `date`."""
	day = _day_of(date)
	filters = [["bom", "is", "set"]]
	if herd:
		filters.append(["name", "=", herd])
	herds = []
	skipped = []
	for h in frappe.get_all("Herds", filters=filters, pluck="name", order_by="name asc"):
		try:
			herds.append(herd_day(h, day))
		except frappe.ValidationError as e:
			# A herd with no animals to feed is not part of the day, not a failure.
			skipped.append({"herd": h, "reason": str(e)})
	return {"date": str(day), "herds": herds, "skipped": skipped, "setup": feeding.setup_gaps()}


def per_animal_intake(herd, date=None):
	"""The herd's animals with what each took against its plan.

	Every animal is credited with an equal share of the herd's day: actual kg /
	head fed, against the planned kg per head.
	"""
	from upande_livestock.serverscripts.common.choices import RETIRED_STATUSES

	day_info = herd_day(herd, date)
	planned, actual = day_info["planned_per_head"], day_info["actual_per_head"]
	animals = []
	for a in frappe.get_all(
		"Animal",
		filters={"current_herd": herd, "docstatus": ["!=", 2], "status": ["not in", RETIRED_STATUSES]},
		fields=["name", "tag_number", "burn_name"],
		order_by="tag_number asc, name asc",
		limit=5000,
	):
		animals.append(
			{
				"animal": a.name,
				"tag": a.tag_number or a.burn_name or a.name,
				"planned_kg": planned,
				"actual_kg": actual,
				"variance_kg": flt(actual - planned, PRECISION),
				"variance_pct": variance_pct(planned, actual),
				"appetite": appetite(actual - planned),
			}
		)
	return {
		"herd": herd,
		"date": day_info["date"],
		"head_count": day_info["head_count"],
		"planned_kg": planned,
		"actual_kg": actual,
		"variance_kg": flt(actual - planned, PRECISION),
		"variance_pct": variance_pct(planned, actual),
		"appetite": appetite(actual - planned),
		"totals": {
			"planned_kg": planned,
			"actual_kg": actual,
			**appetite_totals(animals),
		},
		"animals": animals,
	}


def variance_pct(planned, actual):
	"""Percent above (+) or below (-) the plan, or 0 when nothing was planned."""
	planned = flt(planned)
	if planned <= 0:
		return 0.0
	return flt((flt(actual) - planned) / planned * 100, 1)


# ---------------------------------------------------------------------------
# amending a day
# ---------------------------------------------------------------------------


def _as_components(components):
	"""{item_code: kg} from a list of {item_code, actual_kg} or a plain mapping."""
	components = frappe.parse_json(components) if isinstance(components, str) else components
	if isinstance(components, dict):
		return {str(k): flt(v) for k, v in components.items()}
	out = {}
	for row in components or []:
		code = (row.get("item_code") or "").strip()
		if code:
			out[code] = flt(row.get("actual_kg", row.get("actual")))
	return out


def resync_record(name, for_update=False):
	"""Make a record's status agree with the Stock Entries it links to.

	A day marked Manufactured or Waiting for stock holds only while its entries
	stand. If every linked entry was cancelled or deleted the day returns to
	Planned / Amended (the links are cleared, so it can be amended or mixed
	again); if the waiting draft was posted it is Manufactured. Returns the
	status. Called from `_is_mixed` and from the Stock Entry events in hooks.
	"""
	row = frappe.db.get_value(DOCTYPE, name, ["status", *STOCK_LINKS], as_dict=True, for_update=for_update)
	if not row or row.status not in ("Manufactured", "Waiting for stock"):
		return row.status if row else None
	linked = [row[f] for f in STOCK_LINKS if row[f]]
	docstatus = {
		n: frappe.db.get_value("Stock Entry", n, "docstatus") for n in linked
	}  # None for a deleted entry
	live = [n for n, d in docstatus.items() if d in (0, 1)]
	if linked and not live:
		doc = frappe.get_doc(DOCTYPE, name)
		doc.status = "Planned"  # validate() turns it into Amended when it differs from the plan
		for f in ("work_order", *STOCK_LINKS, "livestock_event"):
			doc.set(f, None)
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		return doc.status
	if row.status == "Waiting for stock" and row.transfer_stock_entry and docstatus.get(row.transfer_stock_entry) == 1:
		frappe.db.set_value(DOCTYPE, name, "status", "Manufactured")
		return "Manufactured"
	return row.status


def on_stock_entry(doc, method=None):
	"""Stock Entry on_submit / on_cancel / on_trash: re-check the feed days linked to it."""
	try:
		names = frappe.get_all(
			DOCTYPE,
			or_filters=[[f, "=", doc.name] for f in STOCK_LINKS],
			filters={"status": ["in", ["Manufactured", "Waiting for stock"]]},
			pluck="name",
		)
		for name in names:
			if method == "on_trash":
				# The entry is going: unlink it first (the link would block the
				# delete), then let the day fall back.
				for f in STOCK_LINKS:
					if frappe.db.get_value(DOCTYPE, name, f) == doc.name:
						frappe.db.set_value(DOCTYPE, name, f, None, update_modified=False)
				frappe.db.set_value(DOCTYPE, name, "status", "Planned", update_modified=False)
				_fall_back_if_empty(name)
			else:
				resync_record(name)
	except Exception:
		frappe.log_error(title="livestock feed day: re-check after a Stock Entry change failed")


def _fall_back_if_empty(name):
	doc = frappe.get_doc(DOCTYPE, name)
	live = [
		getattr(doc, f)
		for f in STOCK_LINKS
		if getattr(doc, f) and frappe.db.get_value("Stock Entry", getattr(doc, f), "docstatus") in (0, 1)
	]
	if live:
		doc.status = "Manufactured"
	else:
		for f in ("work_order", "livestock_event"):
			doc.set(f, None)
		doc.status = "Planned"
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)


def _is_mixed(herd, day, for_update=False):
	"""Is this herd's day already mixed or waiting for stock (by us or the old route)?

	A day we marked mixed is re-checked against its Stock Entries first: if
	they were cancelled or deleted it is not mixed any more.
	"""
	name = _record_name(herd, day)
	if name and resync_record(name, for_update=for_update) in ("Manufactured", "Waiting for stock"):
		return True
	bom = frappe.db.get_value("Herds", herd, "bom")
	item = frappe.db.get_value("BOM", bom, "item") if bom else None
	return bool(item and _issued_on(frappe._dict(item=item), herd, day))


def amend_day(herd, date, components, remarks=None):
	"""Set the actual kg of components for a herd's day. The recipe is untouched.

	`components` is a list of `{item_code, actual_kg}` (or `{item_code: kg}`).
	A component not named keeps its current actual. An item the recipe does not
	have may be added (planned 0). An actual of 0 removes an item that was not
	used at all (it is left out of what is manufactured). Applies to this herd
	and day only. Refused once the day is mixed.
	"""
	day = _day_of(date)
	wanted = _as_components(components)
	if not wanted:
		frappe.throw(_("Enter the kilograms actually fed."))
	for code, kg in wanted.items():
		if kg < 0:
			frappe.throw(_("{0} cannot be a negative amount.").format(code))
		if not frappe.db.exists("Item", code):
			frappe.throw(_("{0} is not a feed item on this site.").format(code))
	if _is_mixed(herd, day):
		frappe.throw(
			_("The feed for {0} on {1} is already mixed. Cancel that feeding before amending the day.").format(
				herd, day
			)
		)

	current = herd_day(herd, day)
	if current["record"]:
		doc = frappe.get_doc(DOCTYPE, current["record"])
	else:
		doc = frappe.new_doc(DOCTYPE)
		doc.update({"date": day, "herd": herd, "head_count": current["head_count"], "bom": current["bom"]})
		for c in current["components"]:
			doc.append(
				"items",
				{
					"item_code": c["item_code"],
					"item_name": c["item_name"],
					"uom": c["uom"],
					"planned_kg": c["planned_kg"],
					"actual_kg": c["planned_kg"],
				},
			)
	by_item = {r.item_code: r for r in doc.items}
	for code, kg in wanted.items():
		row = by_item.get(code)
		if not row:
			item = frappe.db.get_value("Item", code, ["item_name", "stock_uom"], as_dict=True)
			row = doc.append(
				"items", {"item_code": code, "item_name": item.item_name, "uom": item.stock_uom, "planned_kg": 0}
			)
		row.actual_kg = flt(kg, PRECISION)
	if remarks is not None:
		doc.remarks = remarks
	doc.amended_by = frappe.session.user
	doc.amended_on = now_datetime()
	doc.flags.ignore_permissions = True
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	return herd_day(herd, day)


def reset_day(herd, date):
	"""Put a herd's day back to the recipe: drop the amendment, plan = actual.

	The day then loads from the herd's standing recipe again. Refused once the
	day is mixed, like `amend_day`.
	"""
	day = _day_of(date)
	if _is_mixed(herd, day):
		frappe.throw(
			_("The feed for {0} on {1} is already mixed. Cancel that feeding before resetting the day.").format(
				herd, day
			)
		)
	name = _record_name(herd, day)
	if name:
		frappe.delete_doc(DOCTYPE, name, force=True, ignore_permissions=True)
	return herd_day(herd, day)


# ---------------------------------------------------------------------------
# manufacturing the actuals
# ---------------------------------------------------------------------------


def _actual_lines(day_info, base_quantity):
	"""Recipe lines (per BOM batch) that reproduce the day's actuals exactly.

	The tuned BOM keeps the base recipe's batch size, so each line is scaled so
	that, once the Work Order multiplies by (total mixed / batch size), the
	component consumed is its actual kg.
	"""
	total = _total_kg(day_info["components"], "actual_kg")
	lines = []
	for c in day_info["components"]:
		if flt(c["actual_kg"]) <= 0:
			continue
		line = {"item_code": c["item_code"], "qty": flt(c["actual_kg"]) * flt(base_quantity) / total}
		if c["uom"]:
			line["uom"] = c["uom"]
		lines.append(line)
	return lines


def manufacture_day(herd, date=None, employee=None, allow_shortage=False):
	"""Mix and issue the day's ACTUALS for a herd; a short store leaves a draft.

	Without an amendment this is the herd's recipe for the head fed. With one,
	a tuned recipe is minted from the actuals and mixed to the actual total.
	Short stock does not refuse: the transfer is saved as a draft dated the day
	fed and the record says "Waiting for stock".
	"""
	from upande_livestock.serverscripts.feeding._tuned_bom import tuned_bom

	day = _day_of(date)
	# Lock the day's record before judging it: two taps of Mix at once must not
	# both see "not mixed" and both move stock.
	if _is_mixed(herd, day, for_update=True):
		frappe.throw(_("{0} has already been fed on {1}.").format(herd, day))
	info = herd_day(herd, day)
	total = _total_kg(info["components"], "actual_kg")
	if total <= 0:
		frappe.throw(_("Enter the kilograms actually fed before mixing."))
	if not info["head_count"]:
		frappe.throw(_("Enter how many animals were fed."))

	standing = frappe.get_doc("BOM", frappe.db.get_value("Herds", herd, "bom"))
	kwargs = {}
	if info["amended"]:
		kwargs["bom_no"] = tuned_bom(herd, _actual_lines(info, standing.quantity), base_bom=standing.name)
		kwargs["typed_total"] = total

	res = feeding.manufacture_herd_feed(
		herd,
		allow_shortage=allow_shortage,
		employee=employee,
		posting_date=str(day),
		heads=info["head_count"],
		draft_when_short=True,
		**kwargs,
	)

	if info["record"]:
		doc = frappe.get_doc(DOCTYPE, info["record"])
	else:
		doc = frappe.new_doc(DOCTYPE)
		doc.update({"date": day, "herd": herd, "head_count": info["head_count"], "bom": info["bom"]})
		for c in info["components"]:
			doc.append("items", {k: c[k] for k in ("item_code", "item_name", "uom", "planned_kg", "actual_kg")})
	doc.status = "Waiting for stock" if res.get("pending") else "Manufactured"
	doc.work_order = res.get("work_order")
	doc.transfer_stock_entry = res.get("transfer_stock_entry")
	doc.manufacture_stock_entry = res.get("manufacture_stock_entry") or None
	doc.issue_stock_entry = res.get("issue_stock_entry") or None
	doc.livestock_event = res.get("livestock_event")
	doc.flags.ignore_permissions = True
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	out = herd_day(herd, day)
	out.update({"pending": bool(res.get("pending")), "waiting_for": res.get("waiting_for"), "engine": res})
	return out


# ---------------------------------------------------------------------------
# whitelisted
# ---------------------------------------------------------------------------


@frappe.whitelist()
def feed_day_program(date=None, herd=None):
	"""Every herd's formula for a day: planned and actual per component.

	Returns `{ok, date, herds: [{herd, herd_name, date, record, bom, head_count,
	status, amended, planned_kg, actual_kg, planned_per_head, actual_per_head,
	variance_kg, components: [{item_code, item_name, uom, planned_kg, actual_kg,
	planned_per_head, actual_per_head, removed}], draft_entries, stock, remarks}],
	skipped, setup}`.
	"""

	def go():
		guard_read("Herds")
		out = day_program(date, herd)
		out["ok"] = True
		return out

	return run(go, "livestock feed_day_program failed")


@frappe.whitelist()
@idempotent
def amend_feed_day(herd, date, components, remarks=None):
	"""Amend what a herd was actually fed. `components`: `[{item_code, actual_kg}]`;
	an actual of 0 removes an item that was not used.

	Returns `{ok, ...herd_day}`. The herd's recipe is never changed and the
	amendment applies to this herd and day only.
	"""

	def go():
		feed_types.assert_on(feed_types.DAY_SHEET)
		guard(DOCTYPE)
		out = amend_day(herd, date, components, remarks)
		out["ok"] = True
		return out

	return run(go, "livestock amend_feed_day failed")


@frappe.whitelist()
@idempotent
def reset_feed_day(herd, date):
	"""Put a herd's day back to the recipe (drops the amendment). Refused once mixed.

	Returns `{ok, ...herd_day}`.
	"""

	def go():
		feed_types.assert_on(feed_types.DAY_SHEET)
		guard(DOCTYPE)
		out = reset_day(herd, date)
		out["ok"] = True
		return out

	return run(go, "livestock reset_feed_day failed")


@frappe.whitelist()
@idempotent
def manufacture_feed_actuals(herd, date=None, employee=None, allow_shortage=False):
	"""Mix and issue the day's actuals. Short stock leaves a dated draft.

	`employee` is honoured only for a System Manager or Administrator; anyone
	else is always recorded as their own linked Employee.

	Returns `{ok, ...herd_day, pending, waiting_for, engine}`.
	"""

	def go():
		event_types.assert_enabled("Feeding")
		feed_types.assert_on(feed_types.DAY_SHEET)
		guard_stock("Work Order", "Stock Entry")
		# The operator the desk picked (System Manager only), else the user's own.
		who = acting_employee(employee)
		if not who:
			frappe.throw(
				_("No Employee is linked to your user ({0}). Choose who is feeding, or ask HR to link your user to an Employee.").format(
					frappe.session.user
				)
			)
		out = manufacture_day(herd, date, who, allow_shortage=frappe.parse_json(allow_shortage))
		out["ok"] = True
		return out

	return run(go, "livestock manufacture_feed_actuals failed")


@frappe.whitelist()
def animal_intake(herd, date=None):
	"""What each animal in a herd took on a day: actual against planned kg.

	Returns `{ok, herd, date, head_count, planned_kg, actual_kg, variance_kg,
	variance_pct, appetite, totals: {planned_kg, actual_kg, below_plan, above_plan,
	on_plan}, animals: [{animal, tag, planned_kg, actual_kg, variance_kg,
	variance_pct, appetite}]}` (the kg figures are per animal; appetite is
	"below" | "above" | "on_plan", with no threshold).
	"""

	def go():
		guard_read("Herds")
		out = per_animal_intake(herd, date)
		out["ok"] = True
		return out

	return run(go, "livestock animal_intake failed")
