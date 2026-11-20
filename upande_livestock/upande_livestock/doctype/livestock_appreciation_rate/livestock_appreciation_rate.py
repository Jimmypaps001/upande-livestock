# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockAppreciationRate(Document):
	"""One row of the appreciation matrix in Livestock Settings.

	A row prices live weight for animals in a band (calf, weaner, heifer, ...)
	and, optionally, an age range and a weight range. The first row in table
	order that fits an animal is the one used. See
	serverscripts/common/appreciation.py.
	"""

	pass
