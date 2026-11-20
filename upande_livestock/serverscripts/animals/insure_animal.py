# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""insure_animal: split out of animals.animal_cover; that module still re-exports it, so the old dotted path resolves."""

from frappe import _
import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.common import asset_cover


@frappe.whitelist()
def insure_animal(payload):
	"""Put her Asset under a policy. Only Accounts (and System Manager) may for now."""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.animals.animal_cover import _animal, can_insure


	def go():
		guard_read("Animal")
		if not can_insure():
			frappe.throw(_("Only Accounts can insure an animal. Ask Accounts to put {0} under a policy.").format(
				as_dict(payload).get("animal") or _("her")))
		d = as_dict(payload)
		res = asset_cover.put_under_cover(
			_animal(d), d.get("policy"), d.get("sum_insured"),
			d.get("effective_date"), d.get("endorsement_no"))
		return {"ok": True, **res}

	return run(go, "livestock insure_animal failed")
