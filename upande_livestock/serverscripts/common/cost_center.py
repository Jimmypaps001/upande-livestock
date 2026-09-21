"""Which cost centre a livestock stock movement is charged to.

ERPNext refuses a Stock Entry outright — "Cost Center is mandatory for Item
{0}" — when an item's expense account is a profit-and-loss one and no cost
centre can be found for the row. It looks in two places and no further: the
Item Default for that company, then the Company's own default.

On this site neither exists for dairy. Karen Roses, which is the company the
feed engine posts under, has a blank default cost centre; 134 Dairy Feed items,
219 Dairy Drugs and 429 Dairy Others have no buying cost centre; and the Item
Default rows that do exist for the feed meals are against Westwood Dairies and
Kaitet Ltd., with the cost centre empty in both. So the fallback chain runs out
and the run dies. Six of the eight feed runs that failed in the week to
2026-09-21 died exactly there, naming `Dry Cows  Meal`.

Spray met this first and answered it the same way — see
`upande_scp/serverscripts/spray_plan_creator/stock_entry_state.py`, which stamps
the plan's cost centre on every transfer row because ERPNext's own
`make_stock_entry` knows nothing about it. That hook is scoped to Application
Floor Plan work orders, so feed was never covered by it.

## Why a setting rather than fixing the data

Filling in the Company default would charge every stock movement at Karen Roses
to one cost centre, including the flower side, which is not this app's call to
make. Filling in 782 Item Defaults is the right long-term answer but it is a
finance decision per item and it would still leave the next new item to fail.
A setting the dairy owns says what dairy movements cost, changes nothing
outside livestock, and takes effect the moment it is set.

Blank is allowed and means "leave it to ERPNext". Nothing here invents a cost
centre: a wrong one is a real accounting error, quieter and worse than the
refusal it replaced.
"""

import frappe

SETTINGS = "Livestock Settings"


def resolve(company=None):
	"""The cost centre for livestock movements, or None to leave it to ERPNext.

	The setting first, because it is the one a dairy manager can see and change.
	The company default second, so a site that has configured that properly
	needs no setting at all. Never a guess beyond those two.
	"""
	# Asked for by name rather than read straight off the Single: on a site
	# that has this app's code but has not migrated yet the field does not
	# exist, and `get_single_value` raises ValidationError rather than
	# returning nothing. A deploy that lands before its migrate must fall
	# through to the company default, not take feeding down.
	if frappe.get_meta(SETTINGS).has_field("custom_default_cost_center"):
		cc = frappe.db.get_single_value(SETTINGS, "custom_default_cost_center")
		if cc:
			return cc
	if not company:
		company = frappe.db.get_single_value(SETTINGS, "custom_default_company")
	if company:
		return frappe.db.get_value("Company", company, "cost_center") or None
	return None


def stamp(doc, company=None) -> int:
	"""Put that cost centre on every row that has none. Returns how many.

	Only blank rows: a row that already names one was set deliberately, whether
	by an Item Default or by a person, and this is a fallback rather than a
	policy.

	Never raises. A feed run must not be lost because the cost-centre helper
	had a bad day — and if it does nothing, the run fails afterwards with
	ERPNext's own message, which names the item and is what the operator needs.
	"""
	try:
		cc = resolve(company or getattr(doc, "company", None))
		if not cc:
			return 0
		stamped = 0
		for row in doc.get("items") or []:
			if not (row.get("cost_center") or "").strip():
				row.cost_center = cc
				stamped += 1
		return stamped
	except Exception:
		frappe.logger("livestock_cost_center").warning(
			"could not stamp a cost centre; leaving the rows as they were",
			exc_info=True,
		)
		return 0
