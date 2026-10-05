# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Post a livestock stock issue that was saved as a draft for want of stock.

It posts TODAY. The draft carries the day of the event, but the stock was not
there that day — that is why it is a draft — so posting on the event's date
would either be refused or drive that day's balance negative. The issue is the
store handing the items over now; the event keeps its own date.
"""

import frappe
from frappe import _
from frappe.utils import nowtime, today

from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.common.envelope import as_dict, run
from upande_livestock.serverscripts.transactions._drafts import is_livestock_draft


@frappe.whitelist()
def post_stock_draft(payload=None):
	def go():
		if not frappe.has_permission("Stock Entry", "submit"):
			frappe.throw(_("You are not permitted to post stock entries."), frappe.PermissionError)
		name = as_dict(payload).get("name")
		if not name or not is_livestock_draft(name):
			frappe.throw(_("{0} is not a livestock stock entry waiting in draft.").format(name or _("That")))
		se = frappe.get_doc("Stock Entry", name)
		short = livestock_stock.check_availability(
			[{"item_code": d.item_code, "warehouse": d.s_warehouse, "qty": d.qty} for d in se.items]
		)
		if short:
			frappe.throw(
				_("The store still cannot cover {0} — {1}.").format(name, livestock_stock.shortage_message(short))
			)
		se.set_posting_time = 1
		se.posting_date = today()
		se.posting_time = nowtime()
		se.flags.ignore_permissions = True
		se.save()
		se.submit()
		return {"ok": True, "name": se.name}

	return run(go, "livestock post_stock_draft failed")
