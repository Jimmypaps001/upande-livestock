# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Today, as the server counts it, and whether a record may be dated earlier.

Every record screen dates its record. It used to take "today" from the
browser's clock, and the server judged that date by its own: when the two sat
in different time zones the browser's today was the server's yesterday, and a
record nobody had back-dated was refused as backdated. The screens ask here
instead, and while backdating is closed they do not send a date at all.
"""

import frappe
from frappe.utils import today

from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.guards import employee_status


@frappe.whitelist()
def posting_day():
	def go():
		# Every record screen is about animals; whoever may read them may know
		# what day it is to the server.
		guard_read("Animal")
		# is_employee rides along: it is the one extra fact the phone needs when it
		# wakes, and this is the light call it already makes then. A user with no
		# Employee is view-only (guards.require_employee refuses their records).
		return {
			"ok": True,
			"today": today(),
			"backdating_open": backdate.window_open(),
			# The phone's role logic (who may record, who may approve) reads these.
			"roles": sorted(frappe.get_roles()),
			**employee_status(),
		}

	return run(go, "livestock posting_day failed")
