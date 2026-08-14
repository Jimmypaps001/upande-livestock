"""Animal feeding — two-stage flow.

Stage A (manufacture_herd_feed): manufacture a herd's TMR from its BOM.
  Quantity scales with head count: total = heads * BOM.quantity, and every
  raw material = its BOM qty * heads. Creates + submits a Work Order, then a
  "Material Transfer for Manufacture" Stock Entry (raw materials pulled from
  each item's own default warehouse) and a "Manufacture" Stock Entry that
  produces the finished feed. WIP and FG are both the feed store
  (Livestock Settings.custom_feed_wip_warehouse, default
  "Concentrate Mixing Store - KR").

Stage B (feed_herd): issue a chosen quantity of the manufactured feed out of
  the store to the herd via a "Material Issue" Stock Entry, recording the
  operating employee on custom_employee.
"""

import frappe
from frappe.utils import flt, today
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

DEFAULT_FEED_STORE = "Concentrate Mixing Store - KR"


def _feed_store():
	store = frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse")
	return store or DEFAULT_FEED_STORE


def _company():
	return frappe.db.get_single_value("Livestock Settings", "custom_default_company")


def _item_default_warehouse(item_code, company):
	"""The item's own default warehouse for `company`, if configured."""
	return frappe.db.get_value(
		"Item Default",
		{"parent": item_code, "company": company},
		"default_warehouse",
	)


def _herd_bom(herd):
	"""Return (herd_doc, bom_doc, heads). Raises with a clear message on gaps."""
	herd_doc = frappe.get_doc("Herds", herd)
	if not herd_doc.bom:
		frappe.throw("Herd {0} has no BOM linked.".format(herd))
	heads = int(herd_doc.number_of_animals or 0)
	if heads <= 0:
		frappe.throw("Herd {0} has no animals (number_of_animals is 0).".format(herd))
	bom = frappe.get_doc("BOM", herd_doc.bom)
	return herd_doc, bom, heads


@frappe.whitelist()
def get_herd_feed_info(herd):
	"""Preview data for the feeding screens: the per-head BOM scaled by head
	count, the total to manufacture, and how much finished feed is currently
	in the store. Read-only."""
	herd_doc, bom, heads = _herd_bom(herd)
	per_head = flt(bom.quantity) or 1.0
	total_qty = per_head * heads
	store = _feed_store()

	breakdown = []
	for row in bom.items:
		breakdown.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name or row.item_code,
				"per_head_qty": flt(row.qty),
				"total_qty": flt(row.qty) * heads,
				"uom": row.uom or row.stock_uom or "",
			}
		)

	available = frappe.db.get_value("Bin", {"item_code": bom.item, "warehouse": store}, "actual_qty")

	return {
		"herd": herd,
		"bom_no": bom.name,
		"production_item": bom.item,
		"production_item_name": frappe.db.get_value("Item", bom.item, "item_name") or bom.item,
		"heads": heads,
		"per_head_qty": per_head,
		"total_manufacture_qty": total_qty,
		"uom": bom.uom,
		"store": store,
		"available_in_store": flt(available),
		"breakdown": breakdown,
	}


@frappe.whitelist()
def manufacture_herd_feed(herd):
	"""Stage A — manufacture the herd's TMR (Work Order + Transfer + Manufacture).

	Total produced = heads * BOM.quantity; raw materials scale by heads.
	Raw materials are pulled from each item's default warehouse into the feed
	store, then consumed to produce the finished feed back into the store.
	"""
	herd_doc, bom, heads = _herd_bom(herd)
	per_head = flt(bom.quantity) or 1.0
	total_qty = per_head * heads
	store = _feed_store()
	company = _company()

	# 1. Work Order (WIP + FG both = the feed store)
	wo = frappe.new_doc("Work Order")
	wo.production_item = bom.item
	wo.bom_no = bom.name
	wo.qty = total_qty
	wo.company = company
	wo.fg_warehouse = store
	wo.wip_warehouse = store
	wo.transfer_material_against = "Work Order"
	wo.use_multi_level_bom = 0
	wo.skip_transfer = 0
	if wo.meta.has_field("custom_herd"):
		wo.custom_herd = herd
	if wo.meta.has_field("custom_no_of_cows"):
		wo.custom_no_of_cows = heads
	wo.insert(ignore_permissions=True)

	# Source each raw material from its own default warehouse (fall back to store).
	for row in wo.required_items:
		dw = _item_default_warehouse(row.item_code, company)
		row.source_warehouse = dw or store
	wo.save(ignore_permissions=True)
	wo.submit()

	# 2. Material Transfer for Manufacture — raw materials → store (WIP)
	transfer = frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", total_qty))
	transfer.insert(ignore_permissions=True)
	transfer.submit()

	# 3. Manufacture — consume raw materials, produce finished feed into store (FG)
	manufacture = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", total_qty))
	manufacture.insert(ignore_permissions=True)
	manufacture.submit()

	frappe.db.commit()

	return {
		"work_order": wo.name,
		"production_item": bom.item,
		"heads": heads,
		"per_head_qty": per_head,
		"produced_qty": total_qty,
		"uom": bom.uom,
		"store": store,
		"transfer_stock_entry": transfer.name,
		"manufacture_stock_entry": manufacture.name,
	}


@frappe.whitelist()
def feed_herd(herd, qty, employee=None):
	"""Stage B — issue `qty` of the herd's manufactured TMR out of the feed
	store via a Material Issue, recording the operating employee."""
	qty = flt(qty)
	if qty <= 0:
		frappe.throw("Enter a quantity greater than zero.")
	herd_doc, bom, heads = _herd_bom(herd)
	store = _feed_store()
	company = _company()
	item = bom.item

	# The feed issue is a standard Material Issue. This site runs a
	# "PPE Issuance Assignment Creation" script on every Material Issue that
	# requires exactly one employee in custom_employee_data (it only creates
	# PPE assignments for items flagged custom_is_ppe, which feed is not).
	# So we attribute the issue to the currently logged-in employee.
	if not employee:
		employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee:
		frappe.throw(
			"No Employee is linked to your user ({0}). Link one before issuing feed.".format(
				frappe.session.user
			)
		)
	emp_name = frappe.db.get_value("Employee", employee, "employee_name")

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Issue"
	se.purpose = "Material Issue"
	se.company = company
	if se.meta.has_field("custom_employee"):
		se.custom_employee = employee
	if se.meta.has_field("custom_employee_data"):
		emp_row = se.append("custom_employee_data", {})
		emp_row.employee = employee
		emp_row.employee_name = emp_name
	row = se.append("items", {})
	row.item_code = item
	row.qty = qty
	row.s_warehouse = store
	se.remarks = "Animal feeding - {0} - {1} - {2} {3}".format(herd, item, qty, bom.uom or "")
	se.insert(ignore_permissions=True)
	se.submit()
	# No frappe.db.commit() here: it stranded the Stock Entry when the Livestock
	# Event below failed, and defeats the rollback api/operations._run() relies on.
	# The request (or the caller) owns the commit.

	event = _record_feeding_event(herd, item, qty, bom.uom, employee, se.name)

	return {
		"stock_entry": se.name,
		"livestock_event": event,
		"herd": herd,
		"production_item": item,
		"issued_qty": qty,
		"uom": bom.uom,
		"store": store,
		"employee": employee,
	}


def _record_feeding_event(herd, item, qty, uom, employee, stock_entry):
	"""Put the feeding on the herd's timeline as a Feeding Livestock Event.

	Herd-level, with no animal: feed goes to a trough, not to one cow, and
	LivestockEvent.validate() has a matching exemption for exactly this case. One
	event per animal would mean 119 identical rows for a single feed issue.

	The event is best-effort. The feed has physically left the store once the Stock
	Entry submits, so a timeline write that fails must not roll that back and leave
	the books disagreeing with the yard — it warns instead.
	"""
	try:
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Feeding"
		doc.event_date = today()
		doc.current_herd = herd
		doc.operator = employee
		doc.stock_entry = stock_entry
		doc.remarks = "Feed issued: {0} {1} of {2}".format(qty, uom or "", item)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc.name
	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="Livestock feeding event failed")
		frappe.msgprint(
			"Feed was issued ({0}), but the Feeding event was not recorded: {1}".format(stock_entry, str(e)),
			alert=True,
			indicator="orange",
		)
		return None
