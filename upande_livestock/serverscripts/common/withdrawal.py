# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""When an animal may next go to slaughter.

Every Livestock Health Case works out its own `slaughter_safe_date` from the
withdrawal days on its treatments. An animal is only as clear as her latest one,
so the answer is the latest date over her cases, open or closed.
"""

import frappe
from frappe.utils import getdate


def slaughter_safe_date(animal):
	"""The latest `slaughter_safe_date` over the animal's health cases, or None.

	Cancelled cases are ignored; open and closed ones both count, because a
	closed case does not shorten a withdrawal. None means no case holds a date.
	"""
	if not animal:
		return None
	row = frappe.db.sql(
		"""SELECT MAX(slaughter_safe_date) FROM `tabLivestock Health Case`
		   WHERE animal = %s AND docstatus < 2 AND slaughter_safe_date IS NOT NULL""",
		(animal,),
	)
	return getdate(row[0][0]) if row and row[0][0] else None
