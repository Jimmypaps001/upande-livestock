"""Animal feeding — the herd feeding programme.

The farm feeds a herd a TMR that is mixed from raw materials *plus* a
concentrate. There are two kinds of concentrate and they behave differently:

  MIXED      Made on the farm from its own raw materials, so the herd's BOM
             carries it as a sub-assembly line (``BOM Item.bom_no`` set). Short
             stock is answered by manufacturing a batch.
  BOUGHT IN  Arrives ready-packed. Nothing in the item data distinguishes it
             from silage or hay — every feed item sits in the DAIRY group with
             ``is_purchase_item = 1``, the mixed ones included — so these are
             named on Livestock Settings.bought_in_concentrates. Short stock is
             answered by a purchase, not a Work Order.

Work Orders here run with ``use_multi_level_bom = 0`` deliberately. The
concentrate is therefore consumed *as stock*, not exploded — so it has to have
been manufactured first. That is the whole point of the two sections in the UI:

  Main programme      herd -> TMR -> the herd.  Required = BOM line qty * head
                      count, and the batch is issued to the herd as part of the
                      same action: a TMR is mixed and fed, never stored, so
                      manufacturing without issuing left feed sitting on the
                      books that had already gone in the trough.
  Concentrate         concentrate -> stock.  Required = its own BOM, scaled to
                      whole batches covering the TMR's shortfall. This one does
                      stay in the store — it is an input, not a meal.

STORE RESOLUTION
  Livestock Settings.feed_source_warehouses is an ordered list of warehouses
  feed inputs may come from (raw material store, concentrate store, hay store,
  silage pits...), with the WIP/FG store always tried last. ``_pick_source``
  walks it and returns ONE warehouse per line. That same function feeds both
  the availability check and ``Work Order.required_items.source_warehouse``, so
  the shortage the screen reports is the shortage the transfer would really
  hit. Splitting a line across warehouses is deliberately not supported —
  ERPNext carries one source warehouse per required item.
"""

import math

import frappe
from frappe.utils import flt, today
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

DEFAULT_FEED_STORE = "Concentrate Mixing Store - KR"


def _feed_store():
	store = frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse")
	return store or DEFAULT_FEED_STORE


def _company():
	return frappe.db.get_single_value("Livestock Settings", "custom_default_company")


def _feed_source_warehouses():
	"""Ordered candidate warehouses for feed inputs.

	Configured rows first (in grid order), then the WIP/FG store — which must
	always be a candidate, because a concentrate manufactured through this
	module lands there and the TMR run has to be able to consume it.
	"""
	rows = frappe.get_all(
		"Livestock Feed Warehouse",
		filters={"parenttype": "Livestock Settings"},
		fields=["warehouse"],
		order_by="idx asc",
	)
	names = [r.warehouse for r in rows if r.warehouse]
	store = _feed_store()
	if store and store not in names:
		names.append(store)
	return names


def _bin_qty(item_code, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


def _pick_source(item_code, required, warehouses):
	"""Return ``(warehouse, qty_there, qty_everywhere)`` for one line.

	First candidate that can cover `required` in full wins. If none can, the
	warehouse holding the most wins — so the shortfall is reported against a
	real place rather than an arbitrary one.
	"""
	if not warehouses:
		return None, 0.0, 0.0
	qtys = {wh: _bin_qty(item_code, wh) for wh in warehouses}
	total = sum(qtys.values())
	if required <= 0:
		return warehouses[0], qtys[warehouses[0]], total
	for wh in warehouses:
		if qtys[wh] >= required:
			return wh, qtys[wh], total
	best = max(warehouses, key=lambda w: qtys[w])
	return best, qtys[best], total


def _bought_in_concentrates():
	"""Item codes the farm buys ready-packed, from Livestock Settings."""
	return {
		r.item
		for r in frappe.get_all(
			"Livestock Bought In Concentrate",
			filters={"parenttype": "Livestock Settings"},
			fields=["item"],
		)
		if r.item
	}


def _sub_bom_for(row):
	"""The BOM that manufactures a BOM line's item, if it is a sub-assembly."""
	return row.bom_no or frappe.db.get_value("Item", row.item_code, "default_bom")


def resolve_requirement(bom_no, total_qty):
	"""Scale `bom_no` to `total_qty` and price every line against the stores.

	Returns ``(bom_doc, lines)``. Each line carries what the run needs, where it
	would come from, and how far short that warehouse is.
	"""
	bom = frappe.get_doc("BOM", bom_no)
	base = flt(bom.quantity) or 1.0
	factor = flt(total_qty) / base
	warehouses = _feed_source_warehouses()
	bought_in = _bought_in_concentrates()

	lines = []
	for row in bom.items:
		# Everything below is in STOCK UOM, not the recipe UOM. Hay is written in
		# Kilogram on every herd BOM but stocked in BALE (0.07 bale/kg), and Bin
		# and the Stock Entry both count bales — so comparing the recipe figure
		# against Bin.actual_qty would silently read ~14x high. The recipe figure
		# is kept alongside for display, because that is what the mixer works to.
		cf = flt(row.conversion_factor) or 1.0
		required = flt(row.stock_qty or flt(row.qty) * cf) * factor
		wh, here, everywhere = _pick_source(row.item_code, required, warehouses)
		sub_bom = _sub_bom_for(row)
		if sub_bom:
			source = "Mixed"
		elif row.item_code in bought_in:
			source = "Bought in"
		else:
			source = None
		stock_uom = row.stock_uom or row.uom or ""
		recipe_uom = row.uom or stock_uom
		lines.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name or row.item_code,
				"uom": stock_uom,
				"required_qty": required,
				"recipe_qty": flt(row.qty) * factor,
				"recipe_uom": recipe_uom,
				"conversion_factor": cf,
				"source_warehouse": wh,
				"available": here,
				"available_elsewhere": max(0.0, everywhere - here),
				"short_qty": max(0.0, required - here),
				"is_concentrate": bool(source),
				"concentrate_source": source,
				"bom_no": sub_bom,
			}
		)
	return bom, lines


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


# ---------------------------------------------------------------------------
# read — the feeding programme
# ---------------------------------------------------------------------------


def _bought_in_plan(line):
	"""What the screen shows for a concentrate the farm buys ready-packed.

	Same shape as a mixed plan so the UI renders one kind of card, but there is
	no BOM, no batch and no Work Order — a shortfall here is answered by a
	purchase, and the only useful facts are how much is needed and where it is.
	"""
	return {
		"item_code": line["item_code"],
		"item_name": line["item_name"],
		"uom": line["uom"],
		"source": "Bought in",
		"bom_no": None,
		"needed": line["short_qty"] > 0,
		"required_qty": line["required_qty"],
		"short_qty": line["short_qty"],
		"available": line["available"],
		"available_elsewhere": line["available_elsewhere"],
		"source_warehouse": line["source_warehouse"],
		"batch_qty": 0.0,
		"batches": 0,
		"plan_qty": 0.0,
		"lines": [],
		"shortages": [],
		"can_manufacture": False,
	}


def _concentrate_plan(line):
	"""Whole-batch plan for one concentrate line of a herd's TMR.

	Concentrate BOMs are batch recipes (1000 kg is typical), and a mixer runs
	batches, not remainders — so a shortfall rounds up to the next whole batch.
	When nothing is short we still cost one batch, so the operator can see what
	a run would need before committing to it.
	"""
	if not line.get("bom_no"):
		return _bought_in_plan(line)
	sub_bom = frappe.get_doc("BOM", line["bom_no"])
	batch = flt(sub_bom.quantity) or 1.0
	# The shortfall is in the parent line's stock UOM; the sub-BOM's batch is in
	# the sub-BOM's own UOM. They agree for every feed concentrate today, but
	# convert rather than assume.
	short = flt(line["short_qty"])
	if sub_bom.uom and sub_bom.uom == line["recipe_uom"] and sub_bom.uom != line["uom"]:
		short = short / (flt(line["conversion_factor"]) or 1.0)
	batches = int(math.ceil(short / batch)) if short > 0 else 0
	plan_qty = (batches * batch) or batch

	_, sub_lines = resolve_requirement(sub_bom.name, plan_qty)
	return {
		"item_code": line["item_code"],
		"item_name": line["item_name"],
		"uom": line["uom"],
		"source": "Mixed",
		"bom_no": sub_bom.name,
		"needed": short > 0,
		"required_qty": line["required_qty"],
		"short_qty": short,
		"batch_qty": batch,
		"batches": batches,
		"plan_qty": plan_qty,
		"available": line["available"],
		"available_elsewhere": line["available_elsewhere"],
		"source_warehouse": line["source_warehouse"],
		"lines": sub_lines,
		"shortages": [ln for ln in sub_lines if ln["short_qty"] > 0],
		"can_manufacture": not any(ln["short_qty"] > 0 for ln in sub_lines),
	}


@frappe.whitelist()
def get_herd_feeding_program(herd):
	"""Everything the two feeding sections render. Read-only.

	Section 1 is the TMR: head count x per-head BOM, every line priced against
	the stores. Section 2 is one plan per concentrate the TMR draws on.
	"""
	herd_doc, bom, heads = _herd_bom(herd)
	per_head = flt(bom.quantity) or 1.0
	total_qty = per_head * heads
	store = _feed_store()

	bom, lines = resolve_requirement(bom.name, total_qty)
	shortages = [ln for ln in lines if ln["short_qty"] > 0]
	concentrates = [_concentrate_plan(ln) for ln in lines if ln["is_concentrate"]]

	return {
		"herd": herd,
		"herd_label": herd_doc.get("herd_name") or herd,
		"bom_no": bom.name,
		"production_item": bom.item,
		"production_item_name": frappe.db.get_value("Item", bom.item, "item_name") or bom.item,
		"heads": heads,
		"per_head_qty": per_head,
		"total_manufacture_qty": total_qty,
		"uom": bom.uom,
		"store": store,
		"available_in_store": _bin_qty(bom.item, store),
		"warehouses": _feed_source_warehouses(),
		"lines": lines,
		"shortages": shortages,
		"concentrates": concentrates,
		"can_manufacture": not shortages,
	}


@frappe.whitelist()
def get_herd_feed_info(herd):
	"""Back-compat shape for the old feed preview: per-head BOM scaled by head
	count, the total to manufacture, and finished feed on hand."""
	info = get_herd_feeding_program(herd)
	info["breakdown"] = [
		{
			"item_code": ln["item_code"],
			"item_name": ln["item_name"],
			"per_head_qty": ln["required_qty"] / info["heads"] if info["heads"] else 0.0,
			"total_qty": ln["required_qty"],
			"uom": ln["uom"],
		}
		for ln in info["lines"]
	]
	return info


# ---------------------------------------------------------------------------
# write — manufacture
# ---------------------------------------------------------------------------


def _shortage_message(lines):
	return ", ".join(
		"{0} short {1:,.2f} {2}".format(ln["item_name"], ln["short_qty"], ln["uom"] or "").strip()
		for ln in lines
		if ln["short_qty"] > 0
	)


def _assert_can_cover(production_item, bom_no, qty, allow_shortage=False):
	"""Raise if the stores cannot cover this run. Read-only; writes nothing."""
	_, lines = resolve_requirement(bom_no, qty)
	if allow_shortage:
		return lines
	short = [ln for ln in lines if ln["short_qty"] > 0]
	if short:
		frappe.throw(
			"Not enough stock to manufacture {0}: {1}.".format(production_item, _shortage_message(short))
		)
	return lines


def _run_manufacture(production_item, bom_no, qty, herd=None, heads=None, allow_shortage=False):
	"""Work Order -> Material Transfer for Manufacture -> Manufacture.

	One route for both stages. WIP and FG are both the feed store; each required
	item is sourced from the warehouse ``_pick_source`` chose, which is the same
	warehouse the availability check reported on.
	"""
	qty = flt(qty)
	if qty <= 0:
		frappe.throw("Nothing to manufacture — quantity must be greater than zero.")

	store = _feed_store()
	company = _company()
	lines = _assert_can_cover(production_item, bom_no, qty, allow_shortage)
	source_of = {ln["item_code"]: ln["source_warehouse"] for ln in lines}

	wo = frappe.new_doc("Work Order")
	wo.production_item = production_item
	wo.bom_no = bom_no
	wo.qty = qty
	# Set explicitly rather than leaning on the field's `fetch_from`. That fetch
	# stopped firing server-side somewhere after frappe 16.26, so a Work Order
	# built through the API kept the "Nos" default — and Nos is a whole-number
	# UOM, so ERPNext refused every fractional batch ("Qty To Manufacture (319.8)
	# cannot be a fraction"). Feed is measured in kilograms and is fractional by
	# nature, so this has to be right, not merely usually right.
	wo.stock_uom = frappe.db.get_value("Item", production_item, "stock_uom")
	wo.company = company
	wo.fg_warehouse = store
	wo.wip_warehouse = store
	wo.transfer_material_against = "Work Order"
	wo.use_multi_level_bom = 0
	wo.skip_transfer = 0
	if herd and wo.meta.has_field("custom_herd"):
		wo.custom_herd = herd
	if heads and wo.meta.has_field("custom_no_of_cows"):
		wo.custom_no_of_cows = heads
	wo.insert(ignore_permissions=True)

	for row in wo.required_items:
		row.source_warehouse = source_of.get(row.item_code) or store
	wo.save(ignore_permissions=True)
	wo.submit()

	transfer = frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", qty))
	transfer.insert(ignore_permissions=True)
	transfer.submit()

	manufacture = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", qty))
	manufacture.insert(ignore_permissions=True)
	manufacture.submit()

	return {
		"work_order": wo.name,
		"production_item": production_item,
		"bom_no": bom_no,
		"produced_qty": qty,
		"store": store,
		"transfer_stock_entry": transfer.name,
		"manufacture_stock_entry": manufacture.name,
	}


@frappe.whitelist()
def manufacture_herd_feed(herd, allow_shortage=False, employee=None):
	"""Manufacture the herd's TMR and issue the whole batch to that herd.

	Total produced = heads * BOM.quantity; every raw material and the
	concentrate scale by head count. Refuses to run short unless explicitly
	overridden, because the transfer would otherwise post negative stock.

	`employee` attributes the issue; it defaults to the Employee linked to the
	logged-in user, which is what the block sends. That is attribution, not a
	quantity — there is still nothing to choose about how much goes out.

	The batch is issued in the same call, in full. There is no quantity to
	choose: a total mixed ration is made for one herd for one feeding, and
	splitting it would mean the rest sat in the store as feed that had already
	been eaten. Exactly what this run produced goes out — an earlier balance is
	left alone rather than swept up, so each batch reconciles against its own
	issue.

	Nothing is committed here. The manufacture and the issue have to stand or
	fall together, and api/operations._run() relies on the rollback.
	"""
	herd_doc, bom, heads = _herd_bom(herd)
	per_head = flt(bom.quantity) or 1.0
	total_qty = per_head * heads

	# Availability first — it writes nothing, and a shortage is the more useful
	# thing to be told about. The operator is then resolved before anything
	# posts: finding that out afterwards would leave a manufactured batch with
	# no way to move it out, a half-done state that reads as feed in the store.
	_assert_can_cover(bom.item, bom.name, total_qty, frappe.parse_json(allow_shortage))
	employee = _operator_or_throw(employee)

	res = _run_manufacture(
		bom.item, bom.name, total_qty, herd=herd, heads=heads, allow_shortage=frappe.parse_json(allow_shortage)
	)
	issue = _issue_feed(herd, bom, total_qty, employee)
	res.update(
		{
			"heads": heads,
			"per_head_qty": per_head,
			"uom": bom.uom,
			"issued_qty": issue["issued_qty"],
			"issue_stock_entry": issue["stock_entry"],
			"livestock_event": issue["livestock_event"],
			"employee": employee,
		}
	)
	return res


@frappe.whitelist()
def manufacture_concentrate(item_code, qty=None, bom_no=None, allow_shortage=False):
	"""Stage A-prime — manufacture a concentrate so a TMR run can consume it.

	Same Work Order route as the TMR. `qty` defaults to one full batch of the
	concentrate's own BOM.
	"""
	bom_no = bom_no or frappe.db.get_value("Item", item_code, "default_bom")
	if not bom_no:
		frappe.throw("{0} has no default BOM — it cannot be manufactured.".format(item_code))
	bom = frappe.get_doc("BOM", bom_no)
	qty = flt(qty) or (flt(bom.quantity) or 1.0)

	res = _run_manufacture(
		bom.item, bom.name, qty, allow_shortage=frappe.parse_json(allow_shortage)
	)
	frappe.db.commit()
	res["uom"] = bom.uom
	return res


def _operator_or_throw(employee=None):
	"""The Employee the issue is attributed to.

	This site runs a "PPE Issuance Assignment Creation" script on every Material
	Issue that requires exactly one employee in custom_employee_data, so an issue
	without one does not save at all.
	"""
	employee = employee or frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee:
		frappe.throw(
			"No Employee is linked to your user ({0}). Link one before manufacturing feed.".format(
				frappe.session.user
			)
		)
	return employee


@frappe.whitelist()
def feed_herd(herd, qty, employee=None):
	"""Issue `qty` of a herd's TMR out of the store.

	Not the normal path any more — manufacturing issues its own batch. This
	stays for corrections and for clearing a balance left by an earlier run.
	"""
	qty = flt(qty)
	if qty <= 0:
		frappe.throw("Enter a quantity greater than zero.")
	herd_doc, bom, heads = _herd_bom(herd)
	return _issue_feed(herd, bom, qty, _operator_or_throw(employee))


def _issue_feed(herd, bom, qty, employee):
	"""Post the Material Issue and put the feeding on the herd's timeline."""
	store = _feed_store()
	company = _company()
	item = bom.item
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
