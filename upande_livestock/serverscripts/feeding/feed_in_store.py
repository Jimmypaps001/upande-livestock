"""What the feed stores currently hold.

Read-guarded on Item — this discloses stock balances."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding import _engine

# _engine's own docstring records this: every feed item — raw material, mixed
# concentrate and bought-in concentrate alike — sits in the DAIRY item group,
# alongside 700-odd things that are not feed at all (yoghurt SKUs, semen
# straws, drugs, packaging). A chemical or a dairy-processing output such as
# raw milk can still turn up with a balance in a feed warehouse — the store is
# a physical place, not a rule — so this filter is what keeps those off a
# screen meant to answer "what feed do we hold".
#: What the older sites in this group call it. Kept as the default so a site
#: that never fills the setting in behaves exactly as it did before.
DEFAULT_FEED_ITEM_GROUP = "DAIRY"


def feed_item_group():
	"""The item group this farm keeps its feed in.

	Was a constant, and that constant is live's emptiest group: `DAIRY` has no
	items there at all, while the feed sits in `Dairy Feed` (109) and `Dairy
	Others` (409). This page showed an empty store on the site that matters and
	looked like a farm with no feed rather than a page asking the wrong
	question. The drug and semen pickers had the same bug and the same fix.
	"""
	try:
		configured = frappe.db.get_single_value("Livestock Settings", "custom_feed_item_group")
	except Exception:
		configured = None
	return configured or DEFAULT_FEED_ITEM_GROUP


def _ration_roles():
	"""(tmr_items, concentrate_items): item codes by their role in a herd's ration.

	Not "has a BOM" — a TMR is manufactured too, so that test flags TMRs as
	concentrates. Concentrate-ness is a line's role inside a herd's TMR BOM,
	exactly as `_engine.resolve_requirement` already decides it per line: a
	farm-mixed sub-assembly (`_sub_bom_for`) or a bought-in item named on
	Livestock Settings (`_bought_in_concentrates`). A TMR is the production
	item of a BOM some herd actually points at via `Herds.bom` — not every BOM
	in the system, only ones a live ration uses.
	"""
	boms = {h.bom for h in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["bom"]) if h.bom}
	tmr_items = {i for i in (frappe.db.get_value("BOM", bom, "item") for bom in boms) if i}

	bought_in = _engine._bought_in_concentrates()
	concentrate_items = set()
	for bom in boms:
		for row in frappe.get_doc("BOM", bom).items:
			if _engine._sub_bom_for(row) or row.item_code in bought_in:
				concentrate_items.add(row.item_code)
	# A TMR outranks a concentrate role: nothing in the data needs this today,
	# but the two sets should never overlap in what this endpoint reports.
	return tmr_items, concentrate_items - tmr_items


@frappe.whitelist()
def feed_in_store(warehouse=None):
	"""Feed on hand, one row per (item, warehouse), grouped by what it is.

	Backs a Stock page, not the feeding engine — but it reads the engine's own
	notion of where feed lives (`_feed_source_warehouses`) and of what a
	concentrate is (`_ration_roles`, built on `_sub_bom_for` and
	`_bought_in_concentrates`), so this list and what the feeding run actually
	does cannot drift apart.

	Rows are never summed across warehouses. `stock_items` records why: a
	summed balance offers stock a store does not actually have, because the
	rest sits somewhere else on the farm.

	`warehouse` narrows to that one store; left unset, every feed store
	(`_feed_source_warehouses()`) is looked at.

	Every row carries `kind` — "tmr", "concentrate" or "ingredient" — plus
	`is_concentrate` (`kind == "concentrate"`) kept for the caller that only
	asked for a boolean.
	"""

	def go():
		guard_read("Item")
		warehouses = [warehouse] if warehouse else _engine._feed_source_warehouses()
		tmr_items, concentrate_items = _ration_roles()

		rows = []
		if warehouses:
			placeholders = ", ".join(["%s"] * len(warehouses))
			rows = frappe.db.sql(
				f"""SELECT i.name AS item_code, i.item_name, i.stock_uom AS uom,
				           b.actual_qty AS qty, b.warehouse AS warehouse
				    FROM `tabBin` b
				    JOIN `tabItem` i ON i.name = b.item_code
				    WHERE b.warehouse IN ({placeholders})
				      AND b.actual_qty > 0
				      AND IFNULL(i.disabled, 0) = 0
				      AND i.item_group = %s
				    """,
				[*warehouses, feed_item_group()],
				as_dict=True,
			)

		def kind_of(item_code):
			if item_code in tmr_items:
				return "tmr"
			if item_code in concentrate_items:
				return "concentrate"
			return "ingredient"

		items = [
			{
				"item_code": r.item_code,
				"item_name": r.item_name or r.item_code,
				"uom": r.uom,
				"qty": frappe.utils.flt(r.qty),
				"warehouse": r.warehouse,
				"kind": kind_of(r.item_code),
				"is_concentrate": kind_of(r.item_code) == "concentrate",
			}
			for r in rows
		]
		# Finished ration first, then the concentrate that goes into one, then
		# raw ingredients — production order, most-refined first — and
		# alphabetically within each, so the rest reads like a stock list
		# rather than a query dump.
		kind_order = {"tmr": 0, "concentrate": 1, "ingredient": 2}
		items.sort(key=lambda r: (kind_order[r["kind"]], r["item_name"], r["warehouse"]))

		return {"ok": True, "warehouses": warehouses, "items": items}

	return run(go, "livestock feed_in_store failed")
