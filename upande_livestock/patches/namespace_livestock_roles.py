"""Give the module its own roles, cut to the jobs people actually do.

## What was wrong

The app never owned a role. It referenced whatever the site already had —
`Farm Manager`, `Agriculture User`, `Dairy Secretary` and so on — and those grant
near-total access: four of them could read, write, create, delete, submit and
cancel across all sixteen doctypes. There was no such thing as a milker's
permission or a vet's; anyone with livestock access had everything.

The reach was the real problem. **130 people held `Farm Manager` and 267 held
`Agriculture User`**, so roughly 390 people could see and change herd data. Against
that, exactly **four people have ever used the module**, all at Westwood Dairies.

## The six roles

Cut to the jobs, evidenced by what those four actually did:

    Livestock Manager     oversight, herds, disposal, settings   (adopted, re-scoped)
    Livestock Vet         health cases, diagnosis, vaccination
    Livestock Breeder     service, pregnancy diagnosis, calving, births
    Livestock Attendant   feeds herds, manufactures feed, moves animals
    Livestock Milker      daily yield capture
    Livestock Stores      regulates feed stock

`Livestock Manager` is adopted rather than recreated: it already existed, the app
already used it in sixteen permission blocks, and it already fits the naming.

## Why the old roles are not deleted

They appear in **165 Role Profile rows** — `Agriculture User` 60, `Farm Manager` 40,
`Agriculture Manager` 26, `CFU Inspector` 16 and the Dairy variants. Deleting the
Role records would break every profile referencing them, and those profiles serve
modules well beyond livestock. So they are dropped from this app's DocType
permissions instead: the roles survive for whatever else uses them and simply stop
granting livestock access. Same effect, no collateral damage.

## Assignment is by evidence, not by role held

Mapping the old roles across would have re-granted the sprawl. Instead each of the
four active users is given the role their own activity shows:

    yammah@   Service 34, Pregnancy Diagnosis 25  -> Breeder + Vet
    akiptoo@  Calving 11, Preg Diag 8, Birth 5    -> Breeder
    ekoech@   Movement 119                        -> Attendant
    dickson@  Disposals 7, Movements 8, Milk 2    -> Manager

`yammah@` carries Vet as well by the office's decision — the vaccination history
sits under a developer account, so there is no evidence to read for that job.

Milker and Stores are created with no holder. Nobody has ever recorded milk in
anger or manufactured feed, so there is nothing to infer; the office assigns them.

Idempotent, and it adds without removing: an assignment already present is left
alone, so a re-run changes nothing.
"""

import frappe

# The roles this app owns. `Livestock Manager` is deliberately absent — it already
# exists and is adopted as-is.
NEW_ROLES = (
	"Livestock Vet",
	"Livestock Breeder",
	"Livestock Attendant",
	"Livestock Milker",
	"Livestock Stores",
)

# Evidence-led assignment. See the module docstring for what each is based on.
ASSIGNMENTS = {
	"yammah@westwooddairies.com": ("Livestock Breeder", "Livestock Vet"),
	"akiptoo@westwooddairies.com": ("Livestock Breeder",),
	"ekoech@westwooddairies.com": ("Livestock Attendant",),
	"dickson@westwooddairies.com": ("Livestock Manager",),
}


def _ensure_role(role_name):
	"""Create the role if absent. Grants come from the DocType schema, not here."""
	if frappe.db.exists("Role", role_name):
		return False
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": role_name,
			"desk_access": 1,
			"is_custom": 0,
		}
	).insert(ignore_permissions=True)
	return True


def _grant(user, role):
	"""Add a role to a user, unless they already hold it.

	The `Has Role` child row is inserted directly rather than re-saving the User.
	Re-saving revalidates every link the user already carries, and several here are
	dirty — `yammah@` points at a Role Profile `WESTWOOD DAIRY HOD` that no longer
	exists, plus roles `Insights Admin`, `Insights User`, `Dairy Notification` and
	`Visit Approver`. A save fails on those, which would make this patch hostage to
	unrelated rot in someone else's data.

	`ignore_links` scopes the exemption to the one row being added, so the new
	assignment is still validated — only the user's pre-existing mess is stepped
	over. The same trick, for the same reason, as the SCP role patch.
	"""
	if not frappe.db.exists("User", user):
		print(f"[livestock-roles] no such user: {user}")
		return False
	if frappe.db.exists("Has Role", {"parent": user, "role": role, "parenttype": "User"}):
		return False
	frappe.get_doc(
		{
			"doctype": "Has Role",
			"parent": user,
			"parenttype": "User",
			"parentfield": "roles",
			"role": role,
		}
	).insert(ignore_permissions=True, ignore_links=True)
	return True


def execute():
	created = sum(1 for role in NEW_ROLES if _ensure_role(role))
	print(f"[livestock-roles] created {created} of {len(NEW_ROLES)} role(s)")

	granted = 0
	for user, roles in ASSIGNMENTS.items():
		for role in roles:
			if _grant(user, role):
				granted += 1
				print(f"[livestock-roles] {user} -> {role}")
	print(f"[livestock-roles] {granted} assignment(s) added")

	frappe.db.commit()
