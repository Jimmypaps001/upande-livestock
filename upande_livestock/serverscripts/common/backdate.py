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


def resolve(payload: dict, date_key: str | None = None) -> tuple:
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


def assert_not_future(date, what=None) -> None:
	"""Refuse a date later than today.

	FORWARD DATES ARE NOT BACKDATING (see the module docstring) and that is
	deliberate — but it leaves a gap rather than a rule: ``resolve`` answers
	``False`` for tomorrow, so nothing downstream stamps it, relaxes a guard for
	it or suppresses its stock, and a tomorrow-dated request posts real documents
	on a day that has not happened yet. The desk pickers and the handset's
	``DateField`` both cap at today; REST has no picker, so it needs this.

	This is a separate check from backdating, not a change to what backdating
	means: ``resolve``'s forward-date semantics are untouched.
	"""
	if not date:
		return
	if getdate(date) > getdate(today()):
		frappe.throw(_("{0} cannot be in the future.").format(what or _("Date")))


def sanitise(doc, date_field) -> None:
	"""Drop a ``custom_is_backdated`` the document's own date does not support.

	``read_only`` is a desk affordance and nothing more. A client with create
	rights can POST ``custom_is_backdated = 1`` next to today's date over REST and
	collect both privileges the flag carries — the guard exemption in
	``check_guards`` and the stock suppression in ``suppresses_stock`` — for a
	record that is not historical at all.

	The flag stays STORED rather than derived: an honest late entry typed the next
	morning must remain distinguishable from a deliberate history load, so this
	never *sets* the flag. It only clears one that claims history for a day that
	is today or later, which is not a judgement call — it is false.
	"""
	if not doc.meta.has_field("custom_is_backdated") or not doc.get("custom_is_backdated"):
		return
	date = doc.get(date_field)
	if not date or getdate(date) >= getdate(today()):
		doc.custom_is_backdated = 0


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
