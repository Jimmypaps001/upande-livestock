# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the signed-in user may do, in one map the desk SPA reads at boot.

The rule is "if someone should not access something, remove it from their
view". The server already refuses (guard, guard_read, guard_write, guard_stock
and the role checks named below); this answers the same questions up front so
the page can leave out what would only be refused. It asks the SAME questions —
frappe.has_permission for the doctype gates, the very role tuples the endpoints
check for the rest — so the page and the endpoint cannot drift into two rules.

Not an endpoint: it ships inside the page's bootstrap (www/livestock_app.py).
"""

import frappe

# The doctypes the endpoints guard. A page is shown when the user may read what
# its endpoints read; an action when the user may create or write what it writes.
READ = (
	"Animal", "Herds", "Livestock Event", "Livestock Health Case", "Livestock Weight Record",
	"Milk Recording", "Milk Quality Test", "Livestock Disposal", "Livestock Vet", "Livestock Loss",
	"Livestock Loss Scenario", "Livestock Insurance Claim", "Livestock Settings", "BOM", "Item",
	"Work Order", "Notification Log", "Livestock Alert", "Livestock Sire",
)
CREATE = (
	"Livestock Event", "Livestock Health Case", "Livestock Diagnosis", "Livestock Weight Record",
	"Milk Recording", "Milk Quality Test", "Livestock Disposal", "Livestock Vet", "Livestock Loss",
	"Livestock Loss Scenario", "Livestock Insurance Claim", "Herds", "Animal", "BOM",
	"Livestock Feed Actual",
)
WRITE = ("Livestock Disposal", "Livestock Insurance Claim", "Livestock Settings", "BOM", "Animal")


def _roles():
	roles = set(frappe.get_roles())
	if frappe.session.user == "Administrator":
		roles.add("Administrator")
	return roles


def capabilities() -> dict:
	"""The `can` map: per-doctype read/create/write, and the role-gated actions."""
	from upande_livestock.serverscripts.animals.animal_cover import can_insure
	from upande_livestock.serverscripts.common import culling
	from upande_livestock.serverscripts.common.envelope import QUALITY_ROLE, STOCK_ROLES
	from upande_livestock.serverscripts.common.loss import ACCOUNTS_ROLES
	from upande_livestock.serverscripts.feeding._sessions import can_override
	from upande_livestock.serverscripts.common.appreciation import POSTING_ROLES

	roles = _roles()
	admin = "Administrator" in roles
	system = admin or "System Manager" in roles

	def holds(*wanted):
		return admin or bool(roles & set(wanted))

	stock = holds(*STOCK_ROLES, "System Manager")
	return {
		"read": {dt: bool(frappe.has_permission(dt, "read")) for dt in READ},
		"create": {dt: bool(frappe.has_permission(dt, "create")) for dt in CREATE},
		"write": {dt: bool(frappe.has_permission(dt, "write")) for dt in WRITE},
		# guard_stock: the stores and manager roles, or the ERPNext create permissions.
		"stock": stock or all(frappe.has_permission(dt, "create") for dt in ("Work Order", "Stock Entry")),
		# post_stock_draft: the same roles, or submit on Stock Entry.
		"post_draft": holds(*STOCK_ROLES) or bool(frappe.has_permission("Stock Entry", "submit")),
		# feeding._sessions.OVERRIDE_ROLES: feed past the day's plan.
		"override_feed": bool(can_override()),
		# animal_cover.INSURE_ROLES: put an animal under a policy.
		"insure": bool(can_insure()),
		# loss.ACCOUNTS_ROLES: the sale gate and the invoice alert roles.
		"accounts": holds(*ACCOUNTS_ROLES),
		# appreciation.POSTING_ROLES: run asset appreciation now.
		"appreciate": holds(*POSTING_ROLES),
		# culling.assert_vet / assert_manager: the two signatures on a departure.
		"cull_vet": holds(culling.VET_ROLE, "System Manager"),
		"cull_manager": holds(culling.MANAGER_ROLE, "System Manager"),
		# envelope.QUALITY_ROLE (+ the manager): the Quality pages are the lab's and the manager's only.
		"quality": holds(QUALITY_ROLE, "Livestock Manager", "System Manager"),
		# save_sire: the bulls list is the manager's to keep.
		"manage_sires": holds("Livestock Manager", "System Manager"),
		# employee.acting_employee: record on behalf of another Employee.
		"operator": system,
	}
