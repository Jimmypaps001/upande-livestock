"""Which vet did this, for the endpoints that record a veterinary act.

Phone and web both send `vet` (a Livestock Vet name) or nothing. Nothing means
"whoever is signed in, if they are a vet" — a vet recording their own round
should not have to pick themselves. A vet who is not enabled stays on the
records they made but cannot be put on a new one.
"""

import frappe
from frappe import _

from upande_livestock.upande_livestock.doctype.livestock_vet.livestock_vet import vet_for_user


def resolve_vet(d, key="vet"):
	"""The Livestock Vet to stamp on a new record: the one named, else the signed-in
	user's, else None. Throws when the one named does not exist or is disabled."""
	named = (d.get(key) or "").strip() if isinstance(d.get(key), str) else d.get(key)
	if not named:
		return vet_for_user()
	enabled = frappe.db.get_value("Livestock Vet", named, "enabled")
	if enabled is None:
		frappe.throw(_("{0} is not a vet on this farm.").format(named))
	if not enabled:
		frappe.throw(_("{0} is disabled and cannot be recorded against new work.").format(named))
	return named
