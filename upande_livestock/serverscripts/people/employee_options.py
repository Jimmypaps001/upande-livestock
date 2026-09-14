# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who can be named as having done something.

Every Livestock Event records an Employee, and the screens were asking for one
in a free-text box. A box is not a picker: somebody typed "d" and the save came
back "Could not find Operator(technician): d" — a link field refusing a value
that was never going to be one. This is the list the box should always have
been.

Only ACTIVE employees. A record of who did the work is a record about a person
who was there; offering somebody who left last year invites an event that reads
as though they had not.

SEARCHED, NOT LISTED. This company has 2,355 active employees. Shipping all of
them so a farm on a rural connection can scroll to one is a hundred and fifty
kilobytes for a herdsman who was going to type three letters of his own name,
and a dropdown of that length is unusable besides. The caller sends what has
been typed and gets back the first handful that match, by name or by number —
a man who knows his employee number should not have to remember how somebody
spelled him.

Read-guarded on Employee — a staff list is not public.
"""

import frappe

from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run

LIMIT = 25


@frappe.whitelist()
def employee_options(payload=None):
	def go():
		guard_read("Employee")
		d = as_dict(payload)
		q = (d.get("q") or "").strip()
		filters = {"status": "Active"}
		if q:
			filters = [
				["Employee", "status", "=", "Active"],
				[
					"Employee",
					"employee_name" if not q.isdigit() else "name",
					"like",
					f"%{q}%",
				],
			]
		rows = frappe.get_all(
			"Employee",
			filters=filters,
			fields=["name", "employee_name", "designation", "user_id"],
			order_by="employee_name asc",
			limit_page_length=LIMIT,
		)
		return {
			"ok": True,
			"query": q,
			"more": len(rows) >= LIMIT,
			# The Employee linked to whoever is signed in, so a screen never has
			# to ask somebody who the app can already see.
			"mine": current_employee(),
			"employees": [
				{
					"value": r.name,
					"label": r.employee_name or r.name,
					# The id is what the event stores, so it is searchable too —
					# a herdsman who knows his number should not have to
					# remember how his name was spelled.
					"detail": " · ".join(x for x in (r.name, r.designation) if x),
				}
				for r in rows
			],
		}

	return run(go, "livestock employee_options failed")
