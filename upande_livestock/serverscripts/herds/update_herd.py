# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Change a herd's class, weight band, target gain, weighing cadence and
whether it eats a pre-made concentrate."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import guard_write, run

from upande_livestock.serverscripts.feeding._concentrate import CONCENTRATE_MODES

FIELDS = (
	"herd_class", "min_weight_kg", "max_weight_kg", "target_adg_kg", "weigh_monthly", "concentrate_mode"
)


@frappe.whitelist()
def update_herd(
	herd,
	herd_class=None,
	min_weight_kg=None,
	max_weight_kg=None,
	target_adg_kg=None,
	weigh_monthly=None,
	concentrate_mode=None,
):
	"""Update only the fields given; Herds validation judges the result.

	An explicit 0 for the min or max clears that end of the band — the editor
	sends 0s when a herd changes to a class that has no band — so None, not
	falsiness, is what means "leave it alone". The band rules (overlap, gaps,
	one open-ended top band) are the Herds controller's; a refusal comes back as
	the usual error envelope carrying its message.

	`concentrate_mode` is the herd's own answer to "does it eat a pre-made
	concentrate": Farm default (follow Livestock Settings), Pre-manufacture or
	Mix from raw. It changes which feeds its ration may name and whether the
	farm has a concentrate stage at all; it posts nothing.
	"""
	given = {
		"herd_class": herd_class,
		"min_weight_kg": min_weight_kg,
		"max_weight_kg": max_weight_kg,
		"target_adg_kg": target_adg_kg,
		"weigh_monthly": weigh_monthly,
		"concentrate_mode": concentrate_mode,
	}

	def go():
		guard_write("Herds")
		if not frappe.db.exists("Herds", herd):
			frappe.throw(_("There is no herd called {0}.").format(herd))
		if concentrate_mode and concentrate_mode not in CONCENTRATE_MODES:
			frappe.throw(
				_("Concentrate must be one of: {0}.").format(", ".join(CONCENTRATE_MODES))
			)
		doc = frappe.get_doc("Herds", herd)
		# create_herd submits the herds it makes (docstatus 1), and Frappe asks
		# for the "submit" permission to edit a submitted document — which a
		# doctype that is not submittable never grants to anyone. guard_write
		# above is the real check.
		doc.flags.ignore_permissions = True
		for field, value in given.items():
			if value is not None and value != "":
				doc.set(field, value)
		doc.save()
		return {"ok": True, "herd": doc.name, **{f: doc.get(f) for f in FIELDS}}

	return run(go, "livestock update_herd failed")
