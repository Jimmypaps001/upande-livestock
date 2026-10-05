# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Take the fields nothing uses off Herds, and stop submitting herds.

Gone from the DocType:

- `custom_herd_category` only repeated the role flags (every Milking herd on
  the live site is flagged milking, the one Dry herd is flagged dry). The
  phone still gets a `category`, worked out from the flags.
- `custom_production_group` was read by nothing, and on the live site only
  echoed the herd's name.
- `custom_feed_account`, `custom_vet_account` were read by nothing: costs post
  through the herd's cost centre and Livestock Settings.
- `ration_items` (Feeding Ration Item) had no rows on any site; the herd's
  ration is its `bom`.
- `custom_cost_center`, folded into `cost_center` by one_cost_centre_per_herd,
  whose Custom Field record outlived it on the live site.
- `amended_from`, because a herd is a master, not a transaction. Submitting
  one only froze it — the live site had two submitted and ten in draft.

The live site carries these as Custom Field records, not only as DocType
fields, so removing them from herds.json leaves them on the form. The records
are deleted here, along with the Custom Field records for the flags that now
ship in herds.json, which would otherwise be declared twice. Frappe never drops
a column on its own, so the dropped fields' columns go too.

Every herd's head count is recomputed last. It is read-only and kept by
recompute_herd_count, but the live site had drifted (Lactating group 1 read 3
with 4 animals in it), and this is the patch that touches every herd anyway.
"""

import frappe

DROPPED = (
	"custom_herd_category",
	"custom_production_group",
	"custom_feed_account",
	"custom_vet_account",
	"custom_cost_center",
	"ration_items",
	"amended_from",
)
NOW_STANDARD = ("custom_is_milking", "custom_is_dry", "custom_is_calf_rearing")


def execute():
	frappe.db.delete("Custom Field", {"dt": "Herds", "fieldname": ("in", DROPPED + NOW_STANDARD)})
	frappe.db.delete("Property Setter", {"doc_type": "Herds", "field_name": ("in", DROPPED)})

	frappe.db.sql("UPDATE `tabHerds` SET docstatus = 0 WHERE docstatus = 1")

	if frappe.db.exists("DocType", "Feeding Ration Item"):
		frappe.delete_doc("DocType", "Feeding Ration Item", force=True, ignore_missing=True)

	frappe.clear_cache(doctype="Herds")
	for column in DROPPED:
		if column != "ration_items" and frappe.db.has_column("Herds", column):
			frappe.db.sql_ddl(f"ALTER TABLE `tabHerds` DROP COLUMN `{column}`")

	from upande_livestock.serverscripts.common.animal import recompute_herd_count

	for herd in frappe.get_all("Herds", pluck="name"):
		recompute_herd_count(herd)
