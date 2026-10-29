# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who the sire would be for a natural service, before it is saved.

The phone calls this when the user enters a perceived conception date, so it can
show the inferred bull or ask which of several it was. The service endpoints
make the same inference on save (common/sire_inference), so what is shown is
what would be written — unless the user picks someone else, who always wins.
"""

import frappe
from frappe import _
from frappe.utils import today

from upande_livestock.serverscripts.common import sire_inference
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def sire_candidates(animal, conception_date=None):
	"""`{sire_animal, label, inferred, basis, candidates}` for a female and a conception date."""

	def go():
		guard_read("Animal")
		if not frappe.db.exists("Animal", animal):
			frappe.throw(_("{0} is not an animal on this farm.").format(animal))
		got = sire_inference.infer_sire(animal, conception_date or today())
		return {
			"ok": True,
			"animal": animal,
			"conception_date": str(conception_date or today()),
			"sire_animal": got["sire"],
			"label": got["candidates"][0]["label"] if got["sire"] else None,
			"inferred": got["inferred"],
			"basis": got["basis"],
			"candidates": [{k: c[k] for k in ("animal", "label", "basis")} for c in got["candidates"]],
		}

	return run(go, "livestock sire_candidates failed")
