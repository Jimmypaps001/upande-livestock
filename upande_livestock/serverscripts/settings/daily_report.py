# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Daily Report controls on the Settings page.

Read and save for the Daily Report tab of Livestock Settings, which the generic
settings endpoints leave out (see `_shared.DAILY_REPORT_PREFIX`).

Saving writes the named fields and the two child lists directly, never the
whole Single: a full save coerces every unset Int to 0 and switches off the age
and interval guards (see save_livestock_settings). The last-sent date is not
writable from here; only the sender sets it (a site default, outside the form).
"""

import frappe
from frappe import _
from frappe.utils import cint, get_time

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.reports import daily_report

DOCTYPE = "Livestock Settings"
LISTS = {
	"roles": ("daily_report_roles", "Livestock Report Role", "role", "Role"),
	"role_profiles": ("daily_report_role_profiles", "Livestock Report Role Profile", "role_profile", "Role Profile"),
}


def _state():
	doc = frappe.get_single(DOCTYPE)
	send_time = doc.get("daily_report_time") or daily_report.DEFAULT_SEND_TIME
	return {
		"enabled": cint(doc.get("daily_report_enabled")),
		"time": str(get_time(send_time))[:5],
		"head": doc.get("daily_report_head") or "",
		"roles": [r.role for r in doc.get("daily_report_roles") or []],
		"role_profiles": [r.role_profile for r in doc.get("daily_report_role_profiles") or []],
		"last_sent": str(daily_report.last_sent() or "") or None,
		"recipients": daily_report.recipients(doc),
	}


@frappe.whitelist()
def daily_report_settings():
	"""{ok, enabled, time "HH:MM", head, roles[], role_profiles[], last_sent,
	recipients[{user, full_name, email}], can_write, options{users, roles,
	role_profiles}}."""

	def go():
		guard_read(DOCTYPE)
		return {
			"ok": True,
			**_state(),
			"can_write": bool(frappe.has_permission(DOCTYPE, "write")),
			"options": {
				"users": frappe.get_all(
					"User",
					filters={"enabled": 1, "name": ("not in", ("Administrator", "Guest")), "user_type": "System User"},
					fields=["name", "full_name"],
					order_by="full_name asc",
				),
				"roles": frappe.get_all("Role", filters={"disabled": 0}, pluck="name", order_by="name asc"),
				"role_profiles": frappe.get_all("Role Profile", pluck="name", order_by="name asc"),
			},
		}

	return run(go, "livestock daily_report_settings failed")


@frappe.whitelist()
def save_daily_report_settings(payload=None):
	"""Change any of {enabled, time "HH:MM", head, roles[], role_profiles[]};
	fields left out are untouched. Returns the stored state."""

	def go():
		if not frappe.has_permission(DOCTYPE, "write"):
			frappe.throw(_("You are not permitted to change {0}.").format(DOCTYPE), frappe.PermissionError)
		d = as_dict(payload)
		if not isinstance(d, dict) or not d:
			frappe.throw(_("Nothing to save."))

		scalars = {}
		if "enabled" in d:
			scalars["daily_report_enabled"] = 1 if cint(d["enabled"]) else 0
		if "time" in d:
			try:
				t = get_time(str(d["time"]))
			except Exception:
				frappe.throw(_("{0} is not a time. Use hours and minutes, like 18:00.").format(d["time"]))
			if t > daily_report.LATEST_SEND_TIME:
				frappe.throw(_("The report cannot be sent after 23:45. Choose an earlier time."))
			scalars["daily_report_time"] = str(t)
		if "head" in d:
			head = (d["head"] or "").strip()
			if head and not frappe.db.exists("User", head):
				frappe.throw(_("There is no user called {0}.").format(head))
			scalars["daily_report_head"] = head or None
		lists = {}
		for key, (fieldname, child, col, target) in LISTS.items():
			if key not in d:
				continue
			names = d[key] or []
			if not isinstance(names, list):
				frappe.throw(_("The {0} have to be a list.").format(key.replace("_", " ")))
			names = list(dict.fromkeys(str(n).strip() for n in names if str(n).strip()))
			for n in names:
				if not frappe.db.exists(target, n):
					frappe.throw(_("There is no {0} called {1}.").format(target, n))
			lists[key] = names

		for fieldname, value in scalars.items():
			frappe.db.set_single_value(DOCTYPE, fieldname, value)
		for key, names in lists.items():
			fieldname, child, col, _target = LISTS[key]
			frappe.db.delete(child, {"parent": DOCTYPE, "parenttype": DOCTYPE, "parentfield": fieldname})
			for i, n in enumerate(names, start=1):
				row = frappe.new_doc(child)
				row.update({col: n})
				row.parent, row.parenttype, row.parentfield, row.idx = DOCTYPE, DOCTYPE, fieldname, i
				row.insert(ignore_permissions=True)
		frappe.clear_document_cache(DOCTYPE, DOCTYPE)
		return {"ok": True, **_state()}

	return run(go, "livestock save_daily_report_settings failed")
