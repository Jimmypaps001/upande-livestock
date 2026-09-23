"""Which cost centre a livestock stock movement is charged to.

ERPNext refuses a Stock Entry outright — "Cost Center is mandatory for Item
{0}" — when an item's expense account is a profit-and-loss one and no cost
centre can be found for the row (``stock_controller.check_expense_account``).
It looks in two places and no further: the Item Default for that company, then
the Company's own default.

On this site neither exists for dairy: 134 Dairy Feed items, 215 Dairy Drugs
and 429 Dairy Others have no buying cost centre, and the Item Default rows that
do exist for the feed meals leave it empty. So the chain runs out and the run
dies. Six of the eight feed runs in the week to 2026-09-21 died exactly there,
and a new item — `Westwood Dairy Meal - New formulation`, added 2026-09-19 —
took feeding down again on 2026-09-22.

Spray met this first and answered it the same way — see
`upande_scp/serverscripts/spray_plan_creator/stock_entry_state.py`, which stamps
the plan's cost centre on every transfer row because ERPNext's own
`make_stock_entry` knows nothing about it.

## The herd is the first place to look

An earlier version of this module asked a single site-wide setting and then the
company default. That kept the runs alive and charged them to the wrong place:
nine of eleven herds already name `Dairy - KR` and nothing read it, so feed,
milk, drugs and husbandry all landed on `Main - KR` — the flower side of a
company that runs both. A cost centre nobody chose is a real accounting error,
quieter than the refusal it replaced.

So the order is most-specific-first:

    the herd's own cost centre
      -> the Livestock Settings row for that company
        -> the company default, ANNOUNCED as a fallback
          -> nothing, and ERPNext says why

Only the third tier is announced. The farm hand mid-round is not stopped by a
finance setting — the posting goes through — but the message names the herd and
the centre used, so the gap is visible the day it happens rather than at audit.

## Usable, not merely present

Two of ERPNext's own refusals are checked here first, so an unusable answer
lets the chain keep looking instead of dying on it: a **group** cost centre is
never accepted for a transaction, and one belonging to a **different company**
than the entry is rejected outright. Live data has both — herds naming a
Westwood centre while the feed engine posts under Karen Roses.

Blank at the end is allowed and means "leave it to ERPNext". Nothing here
invents a cost centre.
"""

import frappe
from frappe import _

SETTINGS = "Livestock Settings"
SETTINGS_TABLE = "custom_company_cost_centers"
SETTINGS_TABLE_DOCTYPE = "Livestock Cost Center Default"


def usable(cost_center, company=None) -> bool:
	"""Whether ERPNext would accept this cost centre on `company`'s entry.

	A group is never valid on a transaction, and a centre belonging to another
	company is rejected. Unknown or blank is not usable either. Never raises:
	an answer this cannot verify is treated as "keep looking", which is the
	same thing the caller does with a blank.
	"""
	if not (cost_center or "").strip():
		return False
	try:
		row = frappe.db.get_value("Cost Center", cost_center, ["is_group", "company"], as_dict=True)
	except Exception:
		return False
	if not row:
		return False
	if row.is_group:
		return False
	return not (company and row.company and row.company != company)


def _herd_field(herd):
	"""The herd's cost centre, straight off the row.

	Separate so the tier can be tested without a Herds fixture, and so a site
	whose Herds predates the field falls through rather than raising.
	"""
	if not herd:
		return None
	try:
		return frappe.db.get_value("Herds", herd, "cost_center")
	except Exception:
		return None


def herd_cost_center(herd, company=None):
	"""Tier 1. The cost centre this herd is charged to, if it can be used."""
	cc = _herd_field(herd)
	return cc if usable(cc, company) else None


def herd_of(animals):
	"""The herd a drug round is for, or None when the animals disagree.

	Husbandry and health issue drugs for a set of animals, and one Stock
	Entry's rows are per drug rather than per animal — a round covering two
	herds cannot be split between them. So this answers only when every animal
	is in the same herd; otherwise the chain falls to the company tier and says
	so, which is honest in a way that charging one herd for another's drugs
	would not be.
	"""
	if not animals:
		return None
	if isinstance(animals, str):
		animals = [animals]
	herds = set()
	for animal in animals:
		try:
			herd = frappe.db.get_value("Animal", animal, "current_herd")
		except Exception:
			return None
		if not herd:
			return None
		herds.add(herd)
		if len(herds) > 1:
			return None
	return herds.pop() if len(herds) == 1 else None


def _setting_rows():
	"""The per-company rows on Livestock Settings.

	Asked for by name rather than read off the Single: on a site running this
	code before its migrate the table does not exist, and reading it raises
	rather than returning nothing. A deploy that lands before its migrate must
	fall through to the company default, not take feeding down.
	"""
	try:
		if not frappe.get_meta(SETTINGS).has_field(SETTINGS_TABLE):
			return []
		return frappe.get_all(
			SETTINGS_TABLE_DOCTYPE,
			filters={"parenttype": SETTINGS, "parentfield": SETTINGS_TABLE},
			fields=["company", "cost_center"],
			order_by="idx asc",
		)
	except Exception:
		return []


def setting_cost_center(company):
	"""Tier 2. What the dairy configured for this company."""
	if not company:
		return None
	for row in _setting_rows():
		if row.get("company") == company and usable(row.get("cost_center"), company):
			return row.get("cost_center")
	return None


def company_cost_center(company):
	"""Tier 3. ERPNext's own default for the company — the announced fallback."""
	if not company:
		return None
	try:
		cc = frappe.db.get_value("Company", company, "cost_center")
	except Exception:
		return None
	return cc if usable(cc, company) else None


def resolve_with_source(company=None, herd=None):
	"""``(cost_centre, tier)`` where tier is "herd", "setting", "company" or None.

	`stamp` needs the tier, because only the company default is announced.
	"""
	if not company:
		company = frappe.db.get_single_value(SETTINGS, "custom_default_company")

	cc = herd_cost_center(herd, company)
	if cc:
		return cc, "herd"

	cc = setting_cost_center(company)
	if cc:
		return cc, "setting"

	cc = company_cost_center(company)
	if cc:
		return cc, "company"

	return None, None


def resolve(company=None, herd=None):
	"""The cost centre for a livestock movement, or None to leave it to ERPNext."""
	return resolve_with_source(company, herd)[0]


def _announce(cost_center, herd, company):
	"""Say that the posting is on the company default, and where to fix it.

	Never raises: this runs inside a submit, and a message that cannot be
	delivered (a background job, a test, a request that has already responded)
	must not cost the farm its stock entry.
	"""
	try:
		where = (
			_("Herds > {0} > Cost Center").format(herd)
			if herd
			else _("Livestock Settings > Default Cost Centres by Company")
		)
		frappe.msgprint(
			_("Charged to {0}, the default for {1}. Set a cost centre on {2} to charge it correctly.").format(
				frappe.bold(cost_center), company or _("this company"), where
			),
			title=_("Using the fallback cost centre"),
			indicator="orange",
			alert=True,
		)
	except Exception:
		frappe.logger("livestock_cost_center").warning(
			"could not announce the fallback cost centre", exc_info=True
		)


def stamp(doc, company=None, herd=None) -> int:
	"""Put the resolved cost centre on every row that has none. Returns how many.

	Only blank rows: a row that already names one was set deliberately, whether
	by an Item Default or by a person, and this is a fallback rather than a
	policy.

	Never raises. A feed run must not be lost because the cost-centre helper
	had a bad day — and if it does nothing, the run fails afterwards with
	ERPNext's own message, which names the item and is what the operator needs.
	"""
	try:
		company = company or getattr(doc, "company", None)
		cc, source = resolve_with_source(company, herd)
		if not cc:
			return 0
		stamped = 0
		for row in doc.get("items") or []:
			if not (row.get("cost_center") or "").strip():
				row.cost_center = cc
				stamped += 1
		if stamped and source == "company":
			_announce(cc, herd, company)
		return stamped
	except Exception:
		frappe.logger("livestock_cost_center").warning(
			"could not stamp a cost centre; leaving the rows as they were",
			exc_info=True,
		)
		return 0
