# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Every loss of one animal with its claim and disposal."""

import frappe
from frappe import _
from upande_livestock.serverscripts.common import asset_cover

from upande_livestock.serverscripts.common import loss
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def loss_trail(payload=None, animal=None):
	"""Every loss of one animal, newest first, each with its claim and disposal."""

	def go():
		guard_read("Livestock Loss")
		d = loss.merge(payload, animal=animal)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		names = frappe.get_all("Livestock Loss", filters={"animal": d["animal"]}, pluck="name",
		                       order_by="creation desc")
		return {"ok": True, "losses": [loss.trail(n) for n in names], "requirement": loss.required_status(),
		        "cover": asset_cover.cover_for_animal(d["animal"])["state"]}

	return run(go, "livestock loss_trail failed")
