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

NOT WHITELISTED
  These are plain functions. They used to carry ``@frappe.whitelist()``, which
  made them reachable over REST — and because the guards live one layer up in
  the endpoints that call them, callable with no permission check at all. A
  client could manufacture feed or issue stock through this module while the
  guarded twin sat beside it doing the same work. The endpoints in this package
  are the public surface; this is what they call.
"""

import math
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common import stock as livestock_stock

# _availability imports resolve_requirement from this module, so this cannot be
# a top-level import without a circular import (confirmed empirically: bench
# console raises ImportError: cannot import name 'resolve_requirement' from
# partially initialized module). manufacture_herd_feed imports it lazily
# instead, at the one call site that needs it.

DEFAULT_FEED_STORE = "Concentrate Mixing Store - KR"

# The clock time a backdated feed run is stamped with. `posting_date` alone
# means `set_posting_time = 1` with no `posting_time` set — harmless today,
# because ERPNext still fills the gap with "now", but "now" is meaningless for
# a run dated months ago, and a caller that ever passes a genuinely past date
# with the clock past midnight would get a stamp that disagrees with the Work
# Order it belongs to. 06:00 matches `planned_start_date` below, the farm's own
# convention for when a feed run happens, so the Work Order and every Stock
# Entry it produces agree on when the run was.
FEED_RUN_TIME = "06:00:00"

# Which mix a run is, for `common.stock.stock_entry_type_for`. Two jobs, two
# named Stock Entry Types: a concentrate is milled INTO the store as an input,
# a ration is mixed and eaten the same morning. Both used to post as the bare
# "Manufacture" and the ledger could not tell them apart.
CONCENTRATE_MANUFACTURE = "Concentrate Manufacture"
RATION_MANUFACTURE = "Ration Manufacture"


def _is_backdated(posting_date):
	"""True only for a genuinely past date, never for today's.

	`manufacture_herd_feed` is called with `posting_date=today()` for an
	ordinary live run (see test_todays_run_is_untouched_by_the_closed_window),
	not only `None` — so gating the explicit posting_time below on mere
	truthiness would replace today's real clock time with 06:00 for that
	call shape. Only a date earlier than today gets the fixed stamp.
	"""
	return bool(posting_date) and getdate(posting_date) < getdate(today())


# How much later each further same-day backdated run posts. Two backdated runs
# for one herd on one date used to both stamp FEED_RUN_TIME and both price
# against `get_stock_balance` at the same instant, so the second never saw the
# first in the ledger — it read the morning's balance, passed a check it
# should have failed, and only found out at ERPNext's own submit, after a Work
# Order and a transfer already existed. The farm feeds twice, and its second
# feed is an afternoon job, not a same-morning re-run — so the second run of a
# day lands 8 hours after the first (06:00 -> 14:00), a plausible second
# feeding time, not a token minute later. Each further run (more than two in a
# day is a manual correction, not the normal programme) steps another 8 hours.
RUN_TIME_STEP_HOURS = 8

# However many corrections pile onto one day, the last one still has to land
# on THAT day. Capped short of midnight so a pathological run count can never
# roll the posting time into tomorrow, where it would sort after entries that
# have not happened yet.
LAST_RUN_TIME = "23:00:00"


def _run_posting_time(runs_before):
	"""The clock time the (runs_before + 1)th backdated run of a day posts at.

	`runs_before` is how many Material Issue runs already stand for this herd's
	ration item on that date — see `feed_day_status.runs_already_posted`, the
	one place that counts them; nothing here recounts it independently, so the
	two can never disagree about what already happened that day.

	`runs_before == 0` returns `FEED_RUN_TIME` unchanged, so a lone backdated
	run — the common case — behaves exactly as it always has.
	"""
	base = datetime.strptime(FEED_RUN_TIME, "%H:%M:%S")
	cap = datetime.strptime(LAST_RUN_TIME, "%H:%M:%S")
	candidate = base + timedelta(hours=RUN_TIME_STEP_HOURS * runs_before)
	if candidate > cap:
		candidate = cap
	return candidate.strftime("%H:%M:%S")


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


def manufacture_qty(per_head, heads, portion=1.0):
	"""The quantity to manufacture, rounded the way the Work Order will store it.

	87 head at a twentieth of a ration is 4.3500000000000005 in binary floating
	point. The Work Order stores that rounded to 4.35; the Stock Entry was then
	built from the raw value, and ERPNext refused it — "For quantity 4.35 should
	not be greater than allowed quantity 4.35" — because one of them really is
	greater by 5e-16.

	It bites at some head counts and not others: 86 and 88 are exact, 87 and 111
	are not. Lactating Group 1 stood at 111 for months, so this was not a corner
	case waiting to happen. Rounding once, here, means every consumer of the
	number agrees about what it is.
	"""
	precision = cint(frappe.db.get_default("float_precision")) or 3
	return flt(flt(per_head) * flt(heads) * (flt(portion) or 1.0), precision)


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


def get_herd_feeding_program(herd):
	"""Everything the two feeding sections render. Read-only.

	Section 1 is the TMR: head count x per-head BOM, every line priced against
	the stores. Section 2 is one plan per concentrate the TMR draws on.
	"""
	herd_doc, bom, heads = _herd_bom(herd)
	per_head = flt(bom.quantity) or 1.0
	total_qty = manufacture_qty(per_head, heads)
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


def _run_manufacture(
	production_item,
	bom_no,
	qty,
	what,
	herd=None,
	heads=None,
	allow_shortage=False,
	posting_date=None,
	already_verified=False,
	posting_time=FEED_RUN_TIME,
):
	"""Work Order -> Material Transfer for Manufacture -> Manufacture.

	One route for both stages. WIP and FG are both the feed store; each required
	item is sourced from the warehouse ``_pick_source`` chose, which is the same
	warehouse the availability check reported on.

	`what` is which of the two mixes this is — "Concentrate Manufacture" or
	"Ration Manufacture" — and it names the Stock Entry Type the manufacture
	posts under (see ``common.stock.STOCK_ENTRY_TYPES``). Positional and
	required, deliberately: both mixes used to land in the ledger as the bare
	"Manufacture" type and nothing could tell the concentrate mill from the
	mixer wagon, so a new caller must state which it is rather than inherit a
	default. It is passed in rather than inferred from ``production_item``
	because the caller already knows — ``manufacture_concentrate`` is only ever
	a concentrate, ``manufacture_herd_feed`` only ever a ration — while the
	item would have to be guessed at through Livestock Settings, and a farm
	that adds a concentrate without listing it there would silently start
	mislabelling its ledger.

	`posting_date` puts the whole run on a past day. All three documents take it,
	because a transfer dated today feeding a manufacture dated in March is not a
	run that happened — it is two runs that disagree.

	`posting_time` is the clock time to stamp a *backdated* run with (ignored
	for today's date — see `_is_backdated`). Defaults to `FEED_RUN_TIME` for
	every caller but `manufacture_herd_feed`, which passes the staggered time a
	same-day run actually posts at, so this Work Order's `planned_start_date`
	and every Stock Entry it produces agree with the availability check that
	already judged this run against that same instant.

	`already_verified` skips the live-stock check below. Set it when the caller
	has already judged this run against the right ledger — `manufacture_herd_feed`
	always has, against the historical ledger for a backdated run or the live one
	for today's — and judging it again here, unconditionally against today's Bin,
	is not a second opinion: it is a second, DIFFERENT question for a backdated
	run, one that contradicts the first ("the store cannot cover it today" is true
	of a run from last month even when the store covered it back then). Left
	False for `manufacture_concentrate`, which has no check of its own and still
	needs this one.
	"""
	qty = flt(qty)
	if qty <= 0:
		frappe.throw("Nothing to manufacture — quantity must be greater than zero.")

	store = _feed_store()
	company = _company()
	if already_verified:
		_bom, lines = resolve_requirement(bom_no, qty)
	else:
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
	if posting_date:
		wo.planned_start_date = "{0} {1}".format(posting_date, posting_time)
	if herd and wo.meta.has_field("custom_herd"):
		wo.custom_herd = herd
	if heads and wo.meta.has_field("custom_no_of_cows"):
		wo.custom_no_of_cows = heads
	wo.insert(ignore_permissions=True)

	for row in wo.required_items:
		row.source_warehouse = source_of.get(row.item_code) or store
	wo.save(ignore_permissions=True)
	wo.submit()

	def _dated(stock_entry):
		if posting_date:
			stock_entry.set_posting_time = 1
			stock_entry.posting_date = posting_date
			if _is_backdated(posting_date):
				# See FEED_RUN_TIME: without this ERPNext fills the gap with "now",
				# which would put the transfer/manufacture at a different clock
				# time than the Work Order they belong to. Left alone for today's
				# date so a live run keeps stamping its real clock time.
				stock_entry.posting_time = posting_time
		return stock_entry

	transfer = _dated(frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", qty)))
	transfer.insert(ignore_permissions=True)
	transfer.submit()

	manufacture = _dated(frappe.get_doc(make_stock_entry(wo.name, "Manufacture", qty)))
	# `make_stock_entry`'s second argument is the *purpose*, and it leaves
	# `stock_entry_type` equal to it — the generic "Manufacture". Naming the
	# type here keeps the purpose (both named types carry purpose
	# "Manufacture", so Stock Entry's own validate resolves back to it) while
	# the ledger gains the one word that says which mix this was.
	manufacture.stock_entry_type = livestock_stock.stock_entry_type_for(what)
	manufacture.insert(ignore_permissions=True)
	manufacture.submit()

	return {
		"work_order": wo.name,
		"production_item": production_item,
		"bom_no": bom_no,
		"produced_qty": qty,
		"store": store,
		"posting_date": posting_date or today(),
		"transfer_stock_entry": transfer.name,
		"manufacture_stock_entry": manufacture.name,
	}


def manufacture_herd_feed(
	herd,
	allow_shortage=False,
	employee=None,
	portion=1.0,
	posting_date=None,
	bom_no=None,
	heads=None,
	feed_mode="System",
):
	"""Manufacture the herd's TMR and issue the whole batch to that herd.

	Total produced = heads * BOM.quantity; every raw material and the
	concentrate scale by head count. Refuses to run short unless explicitly
	overridden, because the transfer would otherwise post negative stock.

	`employee` attributes the issue; it defaults to the Employee linked to the
	logged-in user, which is what the block sends. That is attribution, not a
	quantity — there is still nothing to choose about how much goes out.

	The batch is issued in the same call, in full. Exactly what this run
	produced goes out — an earlier balance is left alone rather than swept up,
	so each batch reconciles against its own issue. That is the rule this
	function is built on: mixed feed never sits in the store, because it has
	already been eaten by the time anyone would count it.

	`portion` is how a farm that feeds twice a day records it: 0.5 mixes and
	issues half the day's ration, and two such runs make the day. It does not
	break the rule above — each run still issues everything it produced — and a
	day whose portions do not sum to 1 is a real day that happened, not an error
	to refuse. `feed_day_status` is what tells the screen how much of the day is
	left; nothing here enforces it.

	`bom_no` and `heads` override what the herd says. Manual feeding supplies
	both: a tuned recipe, and the number of head actually at the trough, which
	is not always the number on the herd record.

	`posting_date` puts the run on a past day. Availability is then judged
	against the ledger as it stood then, before anything is written, so a run
	that cannot post is refused with a date the operator can act on rather than
	an ERPNext error after two documents already exist.

	A SECOND backdated run for the same herd on the same date is not judged (or
	stamped) at the same instant as the first: see `_run_posting_time`. Both the
	availability check below and every document `_run_manufacture`/`_issue_feed`
	write use that same computed time, so what the check reads is exactly what
	gets posted — this is the whole fix for a second run silently reading the
	morning's stale balance and passing a check it should have failed.

	Nothing is committed here. The manufacture and the issue have to stand or
	fall together, and envelope.run() relies on the rollback.
	"""
	# When the caller states a head count, do not let _herd_bom refuse the run
	# for the herd's own count being zero. A herd record that says 0 while eight
	# animals stand at the trough is exactly the situation manual feeding is for,
	# and the operator has just told us the real number.
	if heads:
		# Resolve the name and check it before loading the document: get_doc("BOM",
		# None) raises DoesNotExistError ("BOM None not found") itself, before
		# `bom` is ever assigned — which reads as an ERPNext internal error
		# instead of the message written for the operator below.
		bom_name = bom_no or frappe.db.get_value("Herds", herd, "bom")
		if not bom_name:
			frappe.throw(_("Herd {0} has no BOM linked.").format(herd))
		bom = frappe.get_doc("BOM", bom_name)
	else:
		herd_doc, bom, herd_heads = _herd_bom(herd)
		if bom_no:
			bom = frappe.get_doc("BOM", bom_no)
		heads = herd_heads
	heads = int(heads)
	if heads <= 0:
		frappe.throw(_("Enter how many animals were fed."))
	per_head = flt(bom.quantity) or 1.0
	portion = flt(portion) or 1.0
	if portion <= 0:
		frappe.throw(_("A feeding run has to be for more than nothing."))
	total_qty = manufacture_qty(per_head, heads, portion)

	# Availability first — it writes nothing, and a shortage is the more useful
	# thing to be told about. The operator is then resolved before anything
	# posts: finding that out afterwards would leave a manufactured batch with
	# no way to move it out, a half-done state that reads as feed in the store.
	backdate.assert_not_future(posting_date, _("Date fed"))
	run_posting_time = FEED_RUN_TIME
	if _is_backdated(posting_date):
		# Feeding is the one backdated write that still MOVES stock — a Work Order
		# and four Stock Entries — so it is the one that most needs the window, and
		# it was the one path that never asked. With the switch off (the default) a
		# backdated weight record was refused while a month-old feed run posted.
		# `assert_allowed(True)` rather than a resolved flag: reaching here already
		# means the date is in the past.
		backdate.assert_allowed(True)
		# Deferred imports — see the note by the top-level imports: both of these
		# import this module (`_availability` imports `resolve_requirement`,
		# `feed_day_status` imports the module wholesale), so importing either at
		# the top would be circular.
		from upande_livestock.serverscripts.feeding import _availability, feed_day_status

		# How many runs already stand for this herd's ration item on this date —
		# the single count `feed_day_status` also shows the operator, read here
		# rather than recounted, so the two can never disagree about the day.
		runs_before = feed_day_status.runs_already_posted(bom.item, herd, posting_date)
		run_posting_time = _run_posting_time(runs_before)
		_availability.assert_can_cover_on(bom.name, total_qty, posting_date, run_posting_time)
	else:
		_assert_can_cover(bom.item, bom.name, total_qty, frappe.parse_json(allow_shortage))
	employee = _operator_or_throw(employee)

	res = _run_manufacture(
		bom.item,
		bom.name,
		total_qty,
		RATION_MANUFACTURE,
		herd=herd,
		heads=heads,
		allow_shortage=frappe.parse_json(allow_shortage),
		posting_date=posting_date,
		# Already judged above — against the historical ledger for a backdated
		# run, or the live one otherwise. _run_manufacture must not judge it a
		# second time against today's Bin: for a backdated run that is a
		# different, contradicting question, and it is exactly how a run the
		# historical check passed was still wrongly refused.
		already_verified=True,
		posting_time=run_posting_time,
	)
	issue = _issue_feed(
		herd,
		bom,
		total_qty,
		employee,
		posting_date=posting_date,
		feed_mode=feed_mode,
		posting_time=run_posting_time,
	)
	res.update(
		{
			"heads": heads,
			"per_head_qty": per_head,
			"portion": portion,
			"uom": bom.uom,
			"feed_mode": feed_mode,
			"issued_qty": issue["issued_qty"],
			"issue_stock_entry": issue["stock_entry"],
			"livestock_event": issue["livestock_event"],
			"employee": employee,
		}
	)
	return res


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
		bom.item,
		bom.name,
		qty,
		CONCENTRATE_MANUFACTURE,
		allow_shortage=frappe.parse_json(allow_shortage),
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


def feed_herd(herd, qty, employee=None, posting_date=None):
	"""Issue `qty` of a herd's TMR out of the store.

	Not the normal path any more — manufacturing issues its own batch. This
	stays for corrections and for clearing a balance left by an earlier run.
	"""
	qty = flt(qty)
	if qty <= 0:
		frappe.throw("Enter a quantity greater than zero.")
	backdate.assert_not_future(posting_date, _("Date fed"))
	if posting_date and getdate(posting_date) < getdate(today()):
		backdate.assert_allowed(True)
	herd_doc, bom, heads = _herd_bom(herd)
	return _issue_feed(herd, bom, qty, _operator_or_throw(employee), posting_date=posting_date)


def _issue_feed(herd, bom, qty, employee, posting_date=None, feed_mode="System", posting_time=FEED_RUN_TIME):
	"""Post the Material Issue and put the feeding on the herd's timeline."""
	store = _feed_store()
	company = _company()
	item = bom.item
	emp_name = frappe.db.get_value("Employee", employee, "employee_name")

	se = frappe.new_doc("Stock Entry")
	# Named rather than generic — see livestock_stock.STOCK_ENTRY_TYPES.
	se.stock_entry_type = livestock_stock.stock_entry_type_for("Feeding")
	se.purpose = "Material Issue"
	se.company = company
	if posting_date:
		se.set_posting_time = 1
		se.posting_date = posting_date
		if _is_backdated(posting_date):
			# See FEED_RUN_TIME: this issue belongs to the same run as the
			# transfer and manufacture above it, so it takes the same clock
			# time — `posting_time` defaults to FEED_RUN_TIME for every caller
			# but `manufacture_herd_feed`, which passes the staggered time a
			# same-day run actually posts at. Left alone for today's date,
			# which keeps its real one.
			se.posting_time = posting_time
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
	# Event below failed, and defeats the rollback envelope.run() relies on.
	# The request (or the caller) owns the commit.

	event = _record_feeding_event(
		herd, item, qty, bom.uom, employee, se.name, event_date=posting_date, feed_mode=feed_mode
	)

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


def _record_feeding_event(herd, item, qty, uom, employee, stock_entry, event_date=None, feed_mode="System"):
	"""Put the feeding on the herd's timeline as a Feeding Livestock Event.

	Herd-level, with no animal: feed goes to a trough, not to one cow, and
	LivestockEvent.validate() has a matching exemption for exactly this case. One
	event per animal would mean 119 identical rows for a single feed issue.

	`event_date` used to be hardcoded to today, which put every backdated run on
	the wrong day of the herd's timeline while its Stock Entry sat on the right
	one — the two records of the same act disagreeing.

	The event is best-effort. The feed has physically left the store once the Stock
	Entry submits, so a timeline write that fails must not roll that back and leave
	the books disagreeing with the yard — it warns instead.
	"""
	event_date = event_date or today()
	try:
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Feeding"
		doc.event_date = event_date
		doc.current_herd = herd
		doc.operator = employee
		doc.stock_entry = stock_entry
		doc.custom_feed_mode = feed_mode
		backdate.stamp(doc, getdate(event_date) < getdate(today()))
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
