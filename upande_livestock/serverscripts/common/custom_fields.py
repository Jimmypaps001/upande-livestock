"""Declarative owner for this app's custom fields on borrowed doctypes.

Work Order, BOM and Stock Entry belong to ERPNext and are shared with three
other installed apps here. Nothing this app adds to them may be assumed to
exist, and nothing it adds may get in anyone else's way.

## Why declared rather than exported

A fixture only restores what was last exported from some site's database, so a
field that was never exported exists nowhere but the machine it was made on.
That is exactly how `Work Order.custom_herd` came to be created by hand on
kaitet.local on 2026-07-14, read by `feeding/ration_history` in raw SQL, and
absent from the live site — where the Rations page died with

    OperationalError (1054): Unknown column 'wo.custom_herd' in 'SELECT'

Declaring the fields here means a reset-to-defaults, a fresh install and a new
site all converge on the same shape. `upande_scp`'s
`store/stock_entry_fields.py` reached this conclusion first and its docstring
says so; this is deliberately the same pattern, down to the reconciliation pass.

## And out of everyone else's way

Every field lives under a **Livestock tab** that only appears when the document
is ours. BOM has always done this: `custom_livestock_tab` gated on
`custom_is_livestock_feed`. Work Order did not — `40ee471` shipped its two
fields anchored on `sales_order` with no tab and no `depends_on`, so a Herd
field and a No. of Cows field appeared on every Work Order on the site, spray
orders included.

Work Order now carries the same gate, on the same fact: `custom_is_livestock_feed`
**fetched from the BOM**, never typed. Not gated on the herd, because a
concentrate run has no herd — it is mixed for the store, not for a group of
cows — and its Work Order is still one of ours.

Stock Entry's milking fields keep the gate they already had
(`stock_entry_type == "Milking"`), which is the same idea expressed against a
field Stock Entry already has.
"""

import frappe

MODULE = "Upande Livestock"
TAB = "custom_livestock_tab"

#: Doctypes this app borrows. A field of ours on one of these that is no longer
#: in the spec is stale and gets removed — see `ensure_livestock_custom_fields`.
MANAGED_DOCTYPES = ("Work Order", "BOM", "Stock Entry")

#: Shown only on a document that is ours.
LIVESTOCK_ONLY = "eval:doc.custom_is_livestock_feed"
MILKING_ONLY = 'eval:doc.stock_entry_type == "Milking"'


def field_spec():
	"""Every custom field this app owns, by doctype, in form order."""
	return {
		"Work Order": [
			{
				"fieldname": TAB,
				"label": "Livestock",
				"fieldtype": "Tab Break",
				# `production_item` exists on every Work Order and is early, so
				# the tab lands after the standard fields rather than among them.
				"insert_after": "production_item",
				"depends_on": LIVESTOCK_ONLY,
				"module": MODULE,
			},
			{
				# The BOM knows whether this is feed; the Work Order asks it.
				# Read-only because nobody types it — and because a typed value
				# could show the tab on a spray order.
				"fieldname": "custom_is_livestock_feed",
				"label": "Is Livestock Feed",
				"fieldtype": "Check",
				"insert_after": TAB,
				"fetch_from": "bom_no.custom_is_livestock_feed",
				"read_only": 1,
				"module": MODULE,
			},
			{
				# Which herd a feed run was mixed for. `feeding/ration_history`
				# SELECTs it, `_engine` writes it, `_tuned_bom` filters on it.
				# Blank on a concentrate run, which is mixed for the store.
				"fieldname": "custom_herd",
				"label": "Herd",
				"fieldtype": "Link",
				"options": "Herds",
				"insert_after": "custom_is_livestock_feed",
				"module": MODULE,
			},
			{
				"fieldname": "custom_no_of_cows",
				"label": "No. of Cows",
				"fieldtype": "Int",
				"insert_after": "custom_herd",
				"module": MODULE,
			},
		],
		"BOM": [
			{
				"fieldname": TAB,
				"label": "Livestock",
				"fieldtype": "Tab Break",
				"insert_after": "custom_work_order",
				"depends_on": LIVESTOCK_ONLY,
				"module": MODULE,
			},
			{
				"fieldname": "custom_herd",
				"label": "Herd",
				"fieldtype": "Link",
				"options": "Herds",
				"insert_after": TAB,
				"module": MODULE,
			},
			{
				"fieldname": "custom_is_livestock_feed",
				"label": "Is Livestock Feed",
				"fieldtype": "Check",
				"insert_after": "custom_herd",
				"module": MODULE,
			},
			{
				"fieldname": "custom_ration_kind",
				"label": "Ration Kind",
				"fieldtype": "Select",
				"options": "\nStanding\nTuned\nConcentrate",
				"description": (
					"Standing = the herd's own template ration (Herds.bom). "
					"Tuned = a one-off copy made for a single feed run. "
					"Concentrate = a mix made for the store, not for a herd."
				),
				"insert_after": "custom_is_livestock_feed",
				"module": MODULE,
			},
		],
		"Stock Entry": [
			{
				"fieldname": "custom_milking_details_section",
				"label": "Milking",
				"fieldtype": "Section Break",
				"insert_after": "posting_time",
				"depends_on": MILKING_ONLY,
				"module": MODULE,
			},
			{
				"fieldname": "custom_milking_time",
				"label": "Milking Time",
				"fieldtype": "Time",
				"insert_after": "custom_milking_details_section",
				"depends_on": MILKING_ONLY,
				"module": MODULE,
			},
			{
				"fieldname": "custom_cows_milked",
				"label": "Cows Milked",
				"fieldtype": "Int",
				"insert_after": "custom_milking_time",
				"depends_on": MILKING_ONLY,
				"module": MODULE,
			},
			{
				# Closes the Milking section so the fields after it — which are
				# not ours and are not about milking — stay where they were.
				"fieldname": "custom_milking_end_section",
				"fieldtype": "Section Break",
				"insert_after": "custom_cows_milked",
				"module": MODULE,
			},
		],
	}


def ensure_livestock_custom_fields():
	"""Make the site match the declaration. Runs on every ``after_migrate``."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	spec = {dt: fields for dt, fields in field_spec().items() if frappe.db.table_exists(dt)}
	if not spec:
		return

	create_custom_fields(spec, update=True)

	# Declarative reconciliation: a field of ours on a managed doctype that the
	# spec no longer claims is stale. Scoped by `module` so this can only ever
	# delete fields this app stamped — SCP's and T&A's are untouched.
	for doctype, fields in spec.items():
		declared = {f["fieldname"] for f in fields}
		for row in frappe.get_all(
			"Custom Field", filters={"dt": doctype, "module": MODULE}, fields=["name", "fieldname"]
		):
			if row.fieldname not in declared:
				frappe.delete_doc("Custom Field", row.name, ignore_permissions=True, force=True)


def remove_livestock_custom_fields():
	"""Delete every field this app owns on the borrowed doctypes (uninstall)."""
	for doctype in MANAGED_DOCTYPES:
		for name in frappe.get_all(
			"Custom Field", filters={"dt": doctype, "module": MODULE}, pluck="name"
		):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
