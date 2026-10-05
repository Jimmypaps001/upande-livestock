# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Post Material Issues for the livestock flows that consume stock.

Vaccination, deworming, treatment and service all take something out of a store.
They share one entry point here so the employee attribution, the failure policy and
the remark format cannot drift apart between them.

TWO THINGS THIS MODULE DELIBERATELY DOES:

1. It attributes every issue to an Employee, in both `custom_employee` and the
   `custom_employee_data` child table. This is not a nicety — this site runs a
   "PPE Issuance Assignment Creation" script on every Material Issue that requires
   exactly one employee in `custom_employee_data`, so an issue without it does not
   save at all. api/feeding.py carries the same workaround.

2. It never commits. api/feeding.py and api/assets.py call frappe.db.commit()
   mid-flow, which breaks the caller's ability to roll back a partially failed
   operation — api/operations._run() relies on that rollback. Committing is the
   caller's business, or the request's.

SHORT STOCK, TODAY: THE RECORD STANDS, THE ISSUE WAITS. This module once
downgraded a failed issue to a warning, which produced 93 vaccinations and 25
health cases with not one gram of stock moved, and nobody noticed. It then
blocked the event instead — so a cow treated this morning could not be
recorded until the store caught up. Now an issue the store cannot cover TODAY
is saved as a draft Stock Entry: the event is recorded, nothing leaves the
store that is not there, and the draft sits on the Transactions page, named
and dated, until somebody posts it. Never silent: the caller's answer carries
`stock_drafts` (see envelope.run), and the page says so.

A BACKDATED issue the store could not cover on the day still blocks: a draft
dated last month posted today would be a different transaction.
`check_availability` reports the gap before anything is written, so the
message names the drug and the shortfall rather than surfacing a raw ERPNext
negative-stock error.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today
from erpnext.stock.utils import get_stock_balance

from upande_livestock.serverscripts.common import cost_center as livestock_cost_center


def default_semen_item():
	return frappe.db.get_single_value("Livestock Settings", "semen_item")


# A Material Issue tells you stock left; it does not tell you why. Naming the
# reason on the Stock Entry Type means a storekeeper reading the stock ledger can
# see a deworming round without opening the document, and a report can group by
# it.
#
# EVERY EVENT IS ITS OWN TYPE: "Livestock " + the event type — Livestock
# Vaccination, Livestock Drying Off, Livestock Check Up — made the first time
# that event posts (and for every posting type on migrate), so a type the farm
# adds in Settings is labelled honestly without a code change. It replaced a
# hand-kept map where Drying Off shared "Animal Treatment" and a new event fell
# through to the bare "Material Issue".
EVENT_TYPE_PREFIX = "Livestock "

# The flows that are not events keep their own names. The two mixes are NOT
# Material Issues — each is the Manufacture leg of a Work Order — and they are
# two different jobs: a concentrate is mixed into the store as an input, a
# ration is mixed and eaten the same morning. Named to match SCP's "Chemical
# Mixing", the same shape of entry. Feeding is the feed engine's daily issue,
# not a recorded event.
STOCK_ENTRY_TYPES = {
	"Feeding": "Animal Feeding",
	"Concentrate Manufacture": "Concentrate Mixing",
	"Ration Manufacture": "Ration Mixing",
}
FALLBACK_TYPE = "Material Issue"
# The generic type to fall back on for the kinds that are not Material Issues.
# A Manufacture entry given "Material Issue" would not merely be labelled
# vaguely, it would be the wrong transaction — ERPNext reads purpose off the
# type — so the fallback has to follow the kind, not the module's majority.
FALLBACK_TYPES = {
	"Concentrate Manufacture": "Manufacture",
	"Ration Manufacture": "Manufacture",
}


def event_stock_entry_type(event_type):
	return f"{EVENT_TYPE_PREFIX}{event_type}"


def ensure_event_stock_entry_type(event_type):
	"""Make "Livestock <event type>" (a Material Issue) if it is missing; return it."""
	name = event_stock_entry_type(event_type)
	if not frappe.db.exists("Stock Entry Type", name):
		doc = frappe.new_doc("Stock Entry Type")
		doc.name = name
		doc.purpose = "Material Issue"
		doc.is_standard = 0
		doc.insert(ignore_permissions=True)
	return name


def ensure_event_stock_entry_types():
	"""after_migrate: a type for every event type set to post stock."""
	if not frappe.db.table_exists("Livestock Event Type") or not frappe.db.table_exists("Stock Entry Type"):
		return
	if not frappe.db.has_column("Livestock Event Type", "posts_stock_entry"):
		return
	for event_type in frappe.get_all("Livestock Event Type", filters={"posts_stock_entry": 1}, pluck="name"):
		ensure_event_stock_entry_type(event_type)
	frappe.db.commit()


def livestock_stock_entry_types():
	"""Every type this app posts under: the events' and the named flows'."""
	names = set(STOCK_ENTRY_TYPES.values())
	names.update(
		frappe.get_all("Stock Entry Type", filters={"name": ["like", f"{EVENT_TYPE_PREFIX}%"]}, pluck="name")
	)
	return sorted(names)


# None of vaccination, deworming, treatment or service carries a time of day —
# only a Date field (LivestockEvent.event_date) — so a backdated issue has
# nothing of its own to be stamped with. `set_posting_time = 1` with no
# `posting_time` set is harmless today, since ERPNext fills the gap with "now",
# but "now" on a day months in the past is not a real time either, and a
# caller that ever runs this after midnight would post a past issue after a
# future one dated the day before. 06:00 is the farm's own convention for
# "when the day's stock work happens" — `_engine.FEED_RUN_TIME` uses the same
# value for the same reason; it is not shared as a single constant because
# importing it here would import `feeding._engine`, which already imports this
# module, and that is circular.
EVENT_POSTING_TIME = "06:00:00"


def stock_entry_type_for(what):
	"""The named type for this kind of issue, or the generic one if unknown.

	An event type gets its own "Livestock <event>" type, made on first use.
	Falling back rather than throwing otherwise: an unknown kind should not stop
	a drug leaving the store, it should just be labelled less precisely.
	"""
	key = (what or "").strip()
	name = STOCK_ENTRY_TYPES.get(key)
	if name:
		return name if frappe.db.exists("Stock Entry Type", name) else FALLBACK_TYPES.get(key, FALLBACK_TYPE)
	if key and frappe.db.exists("Livestock Event Type", key):
		return ensure_event_stock_entry_type(key)
	return FALLBACK_TYPES.get(key, FALLBACK_TYPE)


def check_availability(rows, posting_date=None):
	"""Return the rows the store cannot cover, each with what is missing.

	Read-only. Quantities are summed per (item, warehouse) first, because two
	drug lines naming the same item out of the same store compete for one balance
	— checking them independently would clear a pair that together overdraws it.

	`posting_date` matters: Bin holds today's balance, but a back-dated issue is
	judged against the ledger as it stood then. A health case opened before its
	drug was delivered would otherwise pass a check on today's 24 units and be
	refused by ERPNext for having 0 on the day. When a past date is given the
	balance is read as of that date instead.
	"""
	historic = bool(posting_date) and getdate(posting_date) < getdate(today())
	demand = {}
	for r in rows or []:
		item, wh, qty = r.get("item_code"), r.get("warehouse"), flt(r.get("qty"))
		if not item or not wh or qty <= 0:
			continue
		demand[(item, wh)] = demand.get((item, wh), 0.0) + qty

	short = []
	for (item, wh), qty in demand.items():
		if historic:
			have = flt(get_stock_balance(item, wh, posting_date))
		else:
			have = flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": wh}, "actual_qty"))
		if have + 1e-9 < qty:
			short.append(
				{
					"item_code": item,
					"item_name": frappe.db.get_value("Item", item, "item_name") or item,
					"warehouse": wh,
					"required": qty,
					"available": have,
					"short": qty - have,
					"uom": frappe.db.get_value("Item", item, "stock_uom") or "",
				}
			)
	return short


def shortage_message(short):
	return ", ".join(
		_("{0}: need {1:g} {2}, store has {3:g}").format(s["item_name"], s["required"], s["uom"], s["available"])
		for s in short
	)


def _employee_for(employee=None):
	return employee or frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def issue_items(
	rows, remarks, company=None, posting_date=None, employee=None, what=None, herd=None, draft_if_short=False
):
	"""Post one Material Issue covering `rows`; return the Stock Entry name.

	`rows` is a list of dicts with item_code, qty and warehouse (batch_no and uom
	optional). Rows with no item or a non-positive qty are dropped — a form that
	leaves a drug line blank should not fail, it should issue nothing for it. If
	nothing usable survives, no Stock Entry is created and None is returned.

	Raises when the store cannot cover the rows, naming the drug and the gap —
	unless `draft_if_short` and the issue is for today, when the entry is saved
	as a draft instead and noted for the answer (see the module docstring).

	`herd` is which herd the round was for, and only decides the cost centre —
	see common/cost_center. Optional, because not every caller is about one
	herd; a round spanning two of them passes None and lands on the announced
	company fallback rather than charging one herd for the other's drugs.
	"""
	usable = [r for r in (rows or []) if r.get("item_code") and flt(r.get("qty")) > 0]
	if not usable:
		return None

	missing_wh = [r["item_code"] for r in usable if not r.get("warehouse")]
	if missing_wh:
		frappe.throw(
			_(
				"No source warehouse for {0}. Set one on the row, or set the Drug Store in Livestock Settings."
			).format(", ".join(missing_wh))
		)

	short = check_availability(usable, posting_date=posting_date)
	today_issue = not posting_date or getdate(posting_date) >= getdate(today())
	draft = bool(short) and draft_if_short and today_issue
	if short and not draft:
		frappe.throw(
			_("The store cannot cover this issue on {0} — {1}.").format(
				posting_date or today(), shortage_message(short)
			),
			title=_("Not enough stock"),
		)

	company = (
		company
		or frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		or frappe.defaults.get_user_default("company")
	)
	if not company:
		frappe.throw(_("No company configured (Livestock Settings > Default Company)."))

	employee = _employee_for(employee)
	if not employee:
		frappe.throw(
			_("No Employee is linked to your user ({0}). Link one before issuing stock.").format(
				frappe.session.user
			)
		)

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = stock_entry_type_for(what)
	se.purpose = "Material Issue"
	se.company = company
	if posting_date:
		se.set_posting_time = 1
		se.posting_date = posting_date
		if getdate(posting_date) < getdate(today()):
			# See EVENT_POSTING_TIME. Only for a genuinely past date — a caller
			# that passes today's date explicitly (as a live issue may) keeps
			# stamping its real clock time, exactly as before.
			se.posting_time = EVENT_POSTING_TIME
	# See the module docstring: the PPE script requires exactly one employee here.
	if se.meta.has_field("custom_employee"):
		se.custom_employee = employee
	if se.meta.has_field("custom_employee_data"):
		row = se.append("custom_employee_data", {})
		row.employee = employee
		row.employee_name = frappe.db.get_value("Employee", employee, "employee_name")

	for r in usable:
		item = se.append("items", {})
		item.item_code = r["item_code"]
		item.qty = flt(r["qty"])
		item.s_warehouse = r["warehouse"]
		if r.get("batch_no"):
			item.batch_no = r["batch_no"]
		if r.get("uom"):
			item.uom = r["uom"]

	se.remarks = remarks
	# Drugs hit the same wall as feed: 219 Dairy Drugs carry no buying cost
	# centre and the company has no default, so ERPNext refuses the issue
	# outright. See common/cost_center for why this is a setting and not a
	# repair to 782 Item Defaults.
	livestock_cost_center.stamp(se, company, herd=herd)
	se.insert(ignore_permissions=True)
	if draft:
		note_draft(se, short)
		return se.name
	se.submit()
	return se.name


def note_draft(se, short):
	"""Remember a draft made this request, for the answer to carry."""
	drafts = frappe.flags.get("livestock_stock_drafts") or []
	drafts.append(
		{
			"name": se.name,
			"stock_entry_type": se.stock_entry_type,
			"short": shortage_message(short),
		}
	)
	frappe.flags.livestock_stock_drafts = drafts


def drafts_made():
	"""The drafts this request made (and forget them)."""
	drafts = frappe.flags.get("livestock_stock_drafts") or []
	frappe.flags.livestock_stock_drafts = []
	return drafts


def try_issue_items(rows, remarks, what, **kwargs):
	"""issue_items(), downgrading any failure to a warning. Returns name or None.

	NOT the path for drugs or semen any more — those block, see the module
	docstring. This remains for callers where the stock posting is genuinely
	secondary to the record, and is kept separate so that choice has to be made
	deliberately rather than inherited.
	"""
	try:
		return issue_items(rows, remarks, **kwargs)
	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title=f"Livestock {what} stock issue failed")
		frappe.msgprint(
			_("{0} was recorded, but the stock issue did not post: {1}").format(what, str(e)),
			alert=True,
			indicator="orange",
		)
		return None


def cancel_issues(names):
	"""Cancel the submitted Material Issues among `names`, putting the stock back,
	and delete the drafts among them, so nothing posts later for a record that
	no longer stands.

	A health case or a check-up cancelled used to leave its drug issue posted:
	the Stock Entry does not link back to the document that made it, so Frappe
	never asked. Blank names and entries already cancelled are passed over.
	"""
	for name in {n for n in names or () if n}:
		status = frappe.db.get_value("Stock Entry", name, "docstatus")
		if status == 0:
			discard_draft(name)
			continue
		if status != 1:
			continue
		issue = frappe.get_doc("Stock Entry", name)
		issue.flags.ignore_permissions = True
		issue.cancel()


def discard_draft(name):
	"""Delete a draft issue whose record was cancelled. `force`: the cancelled
	record (and its drug rows) still point at it."""
	if frappe.db.get_value("Stock Entry", name, "docstatus") == 0:
		frappe.delete_doc("Stock Entry", name, ignore_permissions=True, force=True)
