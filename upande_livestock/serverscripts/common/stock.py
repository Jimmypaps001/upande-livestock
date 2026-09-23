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

SHORT STOCK BLOCKS. This module used to downgrade a failed issue to a warning, on
the reasoning that an animal was treated whether or not the balance allows the
issue to post. That produced 93 vaccinations and 25 health cases with not one
gram of stock moved, and nobody noticed. The farm's call is now the opposite: an
issue the store cannot cover stops the event, so the books and the yard cannot
drift apart silently. `check_availability` reports the gap before anything is
written, so the message names the drug and the shortfall rather than surfacing a
raw ERPNext negative-stock error.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today
from erpnext.stock.utils import get_stock_balance

from upande_livestock.serverscripts.common import cost_center as livestock_cost_center


def drug_warehouse():
	return frappe.db.get_single_value("Livestock Settings", "drug_warehouse")


def _drug_warehouse_rows():
	"""The configured drug stores, in grid order.

	Asked for defensively: a site running this code before its migrate has no
	such table, and reading it raises rather than returning nothing.
	"""
	try:
		return frappe.get_all(
			"Livestock Drug Warehouse",
			filters={"parenttype": "Livestock Settings"},
			fields=["warehouse"],
			order_by="idx asc",
		)
	except Exception:
		return []


def drug_source_warehouses():
	"""Ordered stores the drug and semen pickers look in.

	Configured rows first, then the single `drug_warehouse` setting — which
	keeps a site that has configured nothing behaving exactly as it did.

	The single setting alone was not enough on live: it names `Livestock Drug
	Store - KR`, a warehouse with zero Bin rows, while the drugs sit across
	Drug/Medicine Store - Old Office, Westwood Dairy Store, General Store
	Karen, the Delivery Truck and the Clinic Store. Feeding already answers
	this with `_feed_source_warehouses`; this is the same answer.
	"""
	names = [r.warehouse for r in _drug_warehouse_rows() if r.warehouse]
	single = drug_warehouse()
	if single and single not in names:
		names.append(single)
	return names


def semen_warehouse():
	"""The semen store, falling back to the drug store when it is not set apart."""
	return frappe.db.get_single_value("Livestock Settings", "semen_warehouse") or drug_warehouse()


def default_semen_item():
	return frappe.db.get_single_value("Livestock Settings", "semen_item")


# A Material Issue tells you stock left; it does not tell you why. Naming the
# reason on the Stock Entry Type means a storekeeper reading the stock ledger can
# see a deworming round without opening the document, and a report can group by
# it. Every type here is the transaction it was always going to be, labelled
# honestly: the issues carry purpose "Material Issue", the two mixes at the end
# carry "Manufacture". SCP set this precedent with Chemical Spray, Chemical
# Loaning and Chemical Mixing; livestock was still posting everything as the
# generic type.
STOCK_ENTRY_TYPES = {
	"Vaccination": "Vaccination",
	"Deworming": "Deworming",
	"Treatment": "Animal Treatment",
	# Sealing a dry cow's quarters is a treatment, so it shares that type
	# rather than falling through to the bare "Material Issue".
	"Drying Off": "Animal Treatment",
	"Check Up": "Animal Health Check",
	"Service": "Semen Issue",
	"Feeding": "Animal Feeding",
	# The two mixes. These are NOT Material Issues — each is the Manufacture
	# leg of a Work Order — and they are two different jobs on this farm: a
	# concentrate is mixed into the store as an input, a ration is mixed and
	# eaten the same morning. Both were posting as the bare "Manufacture", so
	# the ledger could not tell the mill from the mixer wagon. Named to match
	# SCP's "Chemical Mixing", which is the same shape of entry.
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

	Falling back rather than throwing: a new event type should not stop a drug
	leaving the store, it should just be labelled less precisely until somebody
	adds it here and to the installer.
	"""
	key = (what or "").strip()
	name = STOCK_ENTRY_TYPES.get(key)
	if name and frappe.db.exists("Stock Entry Type", name):
		return name
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


def issue_items(rows, remarks, company=None, posting_date=None, employee=None, what=None, herd=None):
	"""Post one Material Issue covering `rows`; return the Stock Entry name.

	`rows` is a list of dicts with item_code, qty and warehouse (batch_no and uom
	optional). Rows with no item or a non-positive qty are dropped — a form that
	leaves a drug line blank should not fail, it should issue nothing for it. If
	nothing usable survives, no Stock Entry is created and None is returned.

	Raises when the store cannot cover the rows, naming the drug and the gap —
	see the module docstring for why that blocks rather than warns.

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
	if short:
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
	se.submit()
	return se.name


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
