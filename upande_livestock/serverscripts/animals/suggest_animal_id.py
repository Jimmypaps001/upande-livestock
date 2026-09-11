# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What number to offer an animal, and which ones are free beside it."""

import frappe

from upande_livestock.serverscripts.common import animal_id
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def suggest_animal_id(sex=None, birth_date=None):
	"""The number a new animal of this sex and birth year should get.

	Returns the free ones below it too, so a form correcting a number by hand can
	offer them without a second round trip — which is the whole difference
	between "that number is taken" and "that number is taken, try 025."
	"""

	def go():
		guard_read("Animal")
		prefix = animal_id.prefix_for_sex(sex)
		yy = animal_id.year_of(birth_date)
		used = animal_id.taken(prefix, yy)
		return {
			"ok": True,
			"id": animal_id.format_id(prefix, animal_id.next_free(prefix, yy, used=used), yy),
			"prefix": prefix,
			"year": 2000 + yy,
			"gaps": animal_id.gaps(prefix, yy, used=used),
			"gaps_label": animal_id.describe_gaps(prefix, yy, used=used),
			"high_water": max(used) if used else 0,
			"count": len(used),
		}

	return run(go, "livestock suggest_animal_id failed")
