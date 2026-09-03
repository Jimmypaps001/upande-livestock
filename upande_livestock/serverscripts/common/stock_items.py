"""What a livestock form may offer to issue from the store.

Drug and semen pickers must not simply list every Item in the DRUGS/DAIRY item
group — most of a 595-item drug group is not something the store actually
holds, and offering it invites an issue that then fails. `stock_items` scopes
the list to items with real, warehouse-scoped, on-hand quantity instead.
"""

import frappe
from frappe.utils import flt


def stock_items(kind, warehouse=None):
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
