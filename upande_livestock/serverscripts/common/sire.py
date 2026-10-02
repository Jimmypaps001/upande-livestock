"""Who a calf's sire is: the bull whose straw was used on the Service.

Lives here, not in record_birth, because the sire has to be settled where the
Service is resolved. The app's Calving form never sends `related_pregnancy`; the
Service is found by Livestock Event.validate()'s auto-resolver, and any caller
that read the sire before that point (record_birth did) saw nothing. Putting the
resolver in a module both can import covers every write path at once.
"""

import frappe

from upande_livestock.serverscripts.common import event_items
from upande_livestock.serverscripts.common import stock as livestock_stock


def _item_name(code):
	"""The straw's name, or "" when it cannot be named.

	A deleted or renamed Item would otherwise leave a raw code such as
	`4040030118` in a Data field, where it reads exactly like a name. Blank is
	honest; a code that looks like a name is not. A failed lookup must never take
	down a birth record, so it is blank too.
	"""
	try:
		return frappe.db.get_value("Item", code, "item_name") or ""
	except Exception:
		return ""


def _straw_on_the_table(svc, groups):
	"""The first row whose item belongs to a group Service is mapped to.

	The table can also hold a sheath, a glove or a hormone, so row 0 is not
	necessarily the straw. A row is only the straw when its item is in a mapped
	group. Residual risk: if the same group holds straws AND sundries, the first
	of them wins; the configuration cannot say any finer than the group.
	"""
	for row in svc.get("drug_issues") or []:
		code = row.get("item_code")
		if not code:
			continue
		try:
			group = frappe.db.get_value("Item", code, "item_group")
		except Exception:
			continue
		if group in groups:
			return code
	return None


def sire_of(svc):
	"""The bull behind a service, in the order the farm would answer it.

	1. the Sire box, when somebody typed one: an explicit answer wins
	2. the straw on the service's items table (storage when Service is mapped
	   to an item group), restricted to rows in the mapped groups
	3. the straw on the legacy `semen_item` field (services recorded before the
	   table, and sites where Service is unmapped)
	4. when Service is UNMAPPED, the Settings default straw: it is what
	   post_stock_issue actually takes from the store for such a service, so the
	   sire recorded is the straw that left the shelf
	5. blank

	Total: never None, never an exception. The straw's ITEM NAME, not its code.
	"""
	typed = (svc.get("sire") or "").strip()
	if typed:
		return typed

	groups = event_items.groups_for_event("Service")
	straw = _straw_on_the_table(svc, groups) if groups else None
	straw = straw or svc.get("semen_item")
	if not straw and not groups:
		try:
			straw = livestock_stock.default_semen_item()
		except Exception:
			straw = None
	return _item_name(straw) if straw else ""
