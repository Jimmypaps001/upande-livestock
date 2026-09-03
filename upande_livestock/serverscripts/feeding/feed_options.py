"""What the feeding screen offers: the herds a ration can be built for.

Read-guarded on Herds. It had no permission check at all — it answered any
logged-in user on the site, because the desk block was the only caller and the
desk had already authenticated."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def feed_options():
	def go():
		guard_read("Herds")
		herds = frappe.get_all(
			"Herds",
			filters=[["bom", "is", "set"]],
			fields=["name", "herd_name", "number_of_animals", "bom"],
			order_by="herd_name asc",
		)
		return {
			"ok": True,
			"herds": [
				{
					"name": h.name,
					"label": h.herd_name or h.name,
					"heads": int(h.number_of_animals or 0),
					"bom": h.bom,
				}
				for h in herds
			],
		}

	return run(go, "livestock feed_options failed")
