# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Insurance cover of one animal, through Upande Asset (see common/asset_cover)."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import asset_cover
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run


def _animal(d):
	name = (d.get("animal") or "").strip()
	if not name:
		frappe.throw(_("Select an animal."))
	if not frappe.db.exists("Animal", name):
		frappe.throw(_("{0} is not an animal on this farm.").format(name))
	return name


@frappe.whitelist()
def animal_cover(payload=None):
	"""Is she insured, by which policy, until when."""

	def go():
		guard_read("Animal")
		return {"ok": True, **asset_cover.cover_for_animal(_animal(as_dict(payload)))}

	return run(go, "livestock animal_cover failed")


INSURE_ROLES = ("Accounts Manager", "Accounts User", "System Manager")


def can_insure():
	return bool(set(frappe.get_roles()) & set(INSURE_ROLES)) or frappe.session.user == "Administrator"


# The endpoints split out into their own modules. Imported here so the dotted paths the phone and
# the desk already call still resolve (Frappe checks the whitelist by function identity).
# Last, because each of them imports helpers from this module.
from upande_livestock.serverscripts.animals.cover_policies import cover_policies  # noqa: E402,F401
from upande_livestock.serverscripts.animals.insure_animal import insure_animal  # noqa: E402,F401
