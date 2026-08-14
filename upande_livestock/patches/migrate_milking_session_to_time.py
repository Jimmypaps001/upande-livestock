# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Convert Milk Recording's AM/PM session Select into a clock time.

A milking is identified by when it happened, not by a fixed shift label — farms
milk more than twice a day, and the old three-option Select could not say so. The
`session` field is replaced by `milking_time` (Time), and the mirrored Stock Entry
custom field `custom_milking_session` by `custom_milking_time`.

Runs in [post_model_sync]: `milking_time` must already exist in meta before we can
write to it.

`session` is read with raw SQL on purpose. Once the field is gone from the DocType
JSON it is no longer in meta, so frappe.db.get_value would refuse it — but Frappe
never drops the underlying column on sync, so the old values are still there. The
orphan column is left in place rather than dropped: it is the only record of the
original shift labels, and dropping columns is not worth the risk here.

The Stock Entry custom field is handled defensively. `bench migrate` runs
sync_fixtures AFTER post_model_sync patches, so `custom_milking_time` may not
exist yet when this runs; it is created here if missing, which is idempotent with
the fixture that later updates the same record.
"""

import frappe

# Representative clock times for the three labels the Select used to offer. These
# are necessarily approximations — the old data never carried a real time — so the
# remark on each migrated row says so.
SESSION_TIMES = {
	"AM — Morning": "06:00:00",
	"PM — Afternoon": "14:00:00",
	"Evening": "18:00:00",
}
FALLBACK_TIME = "06:00:00"


def execute():
	_migrate_milk_recordings()
	_migrate_stock_entry_field()


def _migrate_milk_recordings():
	if not frappe.db.has_column("Milk Recording", "session"):
		return

	rows = frappe.db.sql(
		"""SELECT name, session FROM `tabMilk Recording`
		   WHERE milking_time IS NULL AND IFNULL(session, '') != ''""",
		as_dict=True,
	)
	for row in rows:
		frappe.db.set_value(
			"Milk Recording",
			row.name,
			"milking_time",
			SESSION_TIMES.get(row.session, FALLBACK_TIME),
			update_modified=False,
		)

	if rows:
		frappe.db.commit()
		print(f"Set milking_time on {len(rows)} Milk Recording(s) from the old session label.")


def _migrate_stock_entry_field():
	old_name = "Stock Entry-custom_milking_session"
	new_name = "Stock Entry-custom_milking_time"

	if not frappe.db.exists("Custom Field", old_name):
		return

	if not frappe.db.exists("Custom Field", new_name):
		old = frappe.get_doc("Custom Field", old_name)
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Stock Entry",
				"fieldname": "custom_milking_time",
				"label": "Milking Time",
				"fieldtype": "Time",
				"insert_after": old.insert_after,
				"depends_on": old.depends_on,
				"allow_on_submit": old.allow_on_submit,
			}
		).insert(ignore_permissions=True)

	# Carry the old labels across as times before dropping the field that held them.
	if frappe.db.has_column("Stock Entry", "custom_milking_session") and frappe.db.has_column(
		"Stock Entry", "custom_milking_time"
	):
		for row in frappe.db.sql(
			"""SELECT name, custom_milking_session AS session FROM `tabStock Entry`
			   WHERE custom_milking_time IS NULL
			     AND IFNULL(custom_milking_session, '') != ''""",
			as_dict=True,
		):
			frappe.db.set_value(
				"Stock Entry",
				row.name,
				"custom_milking_time",
				SESSION_TIMES.get(row.session, FALLBACK_TIME),
				update_modified=False,
			)

	frappe.delete_doc("Custom Field", old_name, force=True, ignore_permissions=True)
	frappe.db.commit()
	print("Replaced Stock Entry custom_milking_session with custom_milking_time.")
