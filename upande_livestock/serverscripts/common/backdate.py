"""What "backdated" means, in one place.

A record is backdated when the day it describes is earlier than the day it was
entered. That is the only definition, and everything that cares — the guards,
the four drug-issuing call sites, the feeding engine — asks here rather than
deciding for itself. Two of them decided for themselves once and disagreed.

Backdating is a property of a *request*, not a separate API. Every write
endpoint in this package already accepts a date; none of them changes shape to
support this. What changes is that the date is now believed.

FORWARD DATES ARE NOT BACKDATING. A date in the future is a different problem
with different rules — a service booked for next week is a plan, not a
historical record — and answering for it here would silently give planning
records the guard exemption that history needs.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

# Feeding is the one backdated event that still moves stock: it is the whole
# point of the manual feeding build. Everything else records what happened and
# leaves the store alone, to be reconciled later from custom_unposted_drugs.
STOCK_MOVING_TYPES = {"Feeding"}


def window_open() -> bool:
	"""True while Livestock Settings says a history load is in progress."""
	return bool(frappe.db.get_single_value("Livestock Settings", "custom_backdating_open"))


def resolve(payload: dict, date_key: str = None) -> tuple:
	"""Return ``(date, is_backdated)`` for a write request.

	Precedence is `event_date`, then the type-specific date, then today —
	deliberately identical to ``common.events.new_livestock_event`` so that the
	date a record is stamped against and the date it is judged by cannot drift
	apart. An empty string counts as absent: a form that clears its date field
	posts "", not a missing key.
	"""
	payload = payload or {}
	raw = payload.get("event_date") or (payload.get(date_key) if date_key else None)
	if not raw:
		return today(), False
	date = getdate(raw)
	return str(date), date < getdate(today())


def assert_allowed(is_backdated: bool) -> None:
	"""Refuse a backdated write while the window is closed."""
	if is_backdated and not window_open():
		frappe.throw(
			_(
				"Backdating is closed. Ask a manager to turn on Backdating Open in "
				"Livestock Settings, or record this against today."
			)
		)


def stamp(doc, is_backdated: bool) -> None:
	"""Mark `doc` as backdated, or explicitly as not.

	Silent when the doctype has no such field — this is called from helpers that
	also build documents which will never carry it.
	"""
	if doc.meta.has_field("custom_is_backdated"):
		doc.custom_is_backdated = 1 if is_backdated else 0


def suppresses_stock(doc_or_type, is_backdated: bool) -> bool:
	"""True when this write must record its consumption without posting it."""
	if not is_backdated:
		return False
	event_type = getattr(doc_or_type, "event_type", doc_or_type)
	return event_type not in STOCK_MOVING_TYPES
