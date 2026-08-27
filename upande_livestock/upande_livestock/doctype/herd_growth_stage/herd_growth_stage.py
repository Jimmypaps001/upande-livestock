# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HerdGrowthStage(Document):
	"""One rung of the growth ladder a heifer climbs before she is served.

	Row order is the movement order — the system reads the table top to bottom to
	work out which herd comes next. The days live here rather than being read out
	of the herd's name: "2-4" is a label somebody chose, not a rule, and deriving
	two months from it would break the first time a farm renamed a herd.
	"""

	pass
