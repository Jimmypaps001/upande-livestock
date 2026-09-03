"""The animals currently in a herd, for a whole-herd husbandry event.

Read-guarded on Animal."""

import frappe

from upande_livestock.serverscripts.common.choices import animal_choices, herd_label_map
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.husbandry._shared import _animals_in_herd


@frappe.whitelist()
def herd_animals(herd):
	"""Active animals in a herd — the target list for a whole-herd round."""

	def go():
		guard_read("Animal")
		labels = herd_label_map()
		animals = _animals_in_herd(herd)
		return {"ok": True, "herd": herd, "animals": animal_choices(animals, labels), "count": len(animals)}

	return run(go, "livestock herd_animals failed")
