"""What the feed stores currently hold.

Read-guarded on Item — this discloses stock balances."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding import _engine


@frappe.whitelist()
def feed_in_store(warehouse=None):
	"""Feed ingredients and concentrates actually on hand, one row per (item, warehouse).

	Backs a Stock page, not the feeding engine — but it reads the engine's own
	notion of where feed lives (`_feed_source_warehouses`) and how a concentrate
	is told apart from a raw material (`_bought_in_concentrates`, plus an
	item's own default BOM), so this list and what the feeding run actually
	does cannot drift apart.

	Rows are never summed across warehouses. `stock_items` records why: a
	summed balance offers stock a store does not actually have, because the
	rest sits somewhere else on the farm.

	`warehouse` narrows to that one store; left unset, every feed store
	(`_feed_source_warehouses()`) is looked at.
	"""

	def go():
		guard_read("Item")
		warehouses = [warehouse] if warehouse else _engine._feed_source_warehouses()
		bought_in = _engine._bought_in_concentrates()

		rows = []
		if warehouses:
			placeholders = ", ".join(["%s"] * len(warehouses))
			rows = frappe.db.sql(
				f"""SELECT i.name AS item_code, i.item_name, i.stock_uom AS uom,
				           b.actual_qty AS qty, b.warehouse AS warehouse,
				           i.default_bom AS default_bom
				    FROM `tabBin` b
				    JOIN `tabItem` i ON i.name = b.item_code
				    WHERE b.warehouse IN ({placeholders})
				      AND b.actual_qty > 0
				      AND IFNULL(i.disabled, 0) = 0
				    """,
				warehouses,
				as_dict=True,
			)

		items = [
			{
				"item_code": r.item_code,
				"item_name": r.item_name or r.item_code,
				"uom": r.uom,
				"qty": frappe.utils.flt(r.qty),
				"warehouse": r.warehouse,
				"is_concentrate": bool(r.default_bom) or r.item_code in bought_in,
			}
			for r in rows
		]
		# Concentrates first — they are what a farm worker checks before deciding
		# whether to mix a batch — then alphabetically, so the rest reads like a
		# stock list rather than a query dump.
		items.sort(key=lambda r: (0 if r["is_concentrate"] else 1, r["item_name"], r["warehouse"]))

		return {"ok": True, "warehouses": warehouses, "items": items}

	return run(go, "livestock feed_in_store failed")
