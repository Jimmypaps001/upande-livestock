"""Install/migrate setup for upande_livestock.

Ensures the master records the app depends on exist on every site, so a fresh
deploy doesn't fail link validation.
"""

import frappe

from upande_livestock.livestock_timings import TIMING_DEFAULTS, read_setting

MILKING_STOCK_ENTRY_TYPE = "Milking"


def ensure_milking_stock_entry_type():
	"""Create the "Milking" Stock Entry Type if it's missing.

	Livestock Settings.custom_milking_stock_entry_type defaults to "Milking"
	and Milk Recording posts its milk Stock Entry under that type. Neither
	ERPNext nor our fixtures ship the record, so on a fresh deploy the first
	save of Livestock Settings fails with:

	    LinkValidationError: Could not find Milking Stock Entry Type: Milking

	Milk is received into a warehouse (t_warehouse only), so the entry type is a
	Material Receipt. Idempotent — safe to run on every install and migrate.
	"""
	# Stock Entry Type is an ERPNext core doctype; skip if unavailable.
	if not frappe.db.table_exists("Stock Entry Type"):
		return
	if frappe.db.exists("Stock Entry Type", MILKING_STOCK_ENTRY_TYPE):
		return

	doc = frappe.new_doc("Stock Entry Type")
	doc.name = MILKING_STOCK_ENTRY_TYPE  # autoname is Prompt
	doc.purpose = "Material Receipt"
	doc.insert(ignore_permissions=True)
	frappe.db.commit()


SEED_EVENT_TYPES = [
	{"name": "Feeding", "creates_animal": 0, "detail_doctype": None},
	{"name": "Milking", "creates_animal": 0, "detail_doctype": None},
	{"name": "Movement", "creates_animal": 0, "detail_doctype": None},
	{"name": "Service", "creates_animal": 0, "detail_doctype": None},
	{"name": "Pregnancy Diagnosis", "creates_animal": 0, "detail_doctype": None},
	{"name": "Calving", "creates_animal": 0, "detail_doctype": None},
	{"name": "Birth", "creates_animal": 1, "detail_doctype": None},
	{"name": "Abortion", "creates_animal": 0, "detail_doctype": None},
	{"name": "Drying Off", "creates_animal": 0, "detail_doctype": None},
	{"name": "Vaccination", "creates_animal": 0, "detail_doctype": None},
	{"name": "Deworming", "creates_animal": 0, "detail_doctype": None},
	{"name": "Heat Detection", "creates_animal": 0, "detail_doctype": None},
	{"name": "Weight Recording", "creates_animal": 0, "detail_doctype": None},
	{"name": "Hoof Trimming", "creates_animal": 0, "detail_doctype": None},
	{"name": "Dehorning", "creates_animal": 0, "detail_doctype": None},
	{"name": "Check Up", "creates_animal": 0, "detail_doctype": "Livestock Diagnosis"},
	{"name": "Health Case", "creates_animal": 0, "detail_doctype": "Livestock Health Case"},
]


def ensure_livestock_event_types():
	"""Create the Livestock Event Type records the app relies on.

	Idempotent. Also creates a record for any event_type value already present in
	tabLivestock Event, so a site carrying a type we did not anticipate does not end
	up with a dangling Link once event_type becomes a Link field.
	"""
	if not frappe.db.table_exists("Livestock Event Type"):
		return

	for seed in SEED_EVENT_TYPES:
		if frappe.db.exists("Livestock Event Type", seed["name"]):
			continue
		doc = frappe.new_doc("Livestock Event Type")
		doc.name = seed["name"]  # autoname is Prompt
		doc.is_active = 1
		doc.creates_animal = seed["creates_animal"]
		if seed["detail_doctype"]:
			doc.detail_doctype = seed["detail_doctype"]
		doc.insert(ignore_permissions=True)

	if frappe.db.table_exists("Livestock Event"):
		existing = frappe.db.sql_list(
			"SELECT DISTINCT event_type FROM `tabLivestock Event` WHERE IFNULL(event_type, '') != ''"
		)
		for event_type in existing:
			if frappe.db.exists("Livestock Event Type", event_type):
				continue
			doc = frappe.new_doc("Livestock Event Type")
			doc.name = event_type
			doc.is_active = 1
			doc.insert(ignore_permissions=True)

	frappe.db.commit()


def ensure_livestock_timing_defaults():
	"""Seed `tabSingles` with the real default for any timing field with no row.

	Livestock Settings is a Single. A field with no row in `tabSingles` loads
	as `None` in Python — and the next save of the doctype (through the desk
	UI, editing any unrelated field, for any reason) coerces that `None`
	through `cint()` and persists an explicit `0` (see
	`frappe.model.base_document.BaseDocument.get_valid_dict`). That silently
	disables every breeding timing (or worse: `gestation_period_days = 0`
	makes the expected calving date equal the service date) the first time
	anyone opens the settings page and clicks Save — indistinguishable
	afterwards from a deliberate choice, since `get_timing()` correctly
	honours a configured 0.

	Only fills in fields with no row at all (per `read_setting`, not
	`frappe.db.get_single_value`, for the same casting reason `get_timing`
	avoids it) — never overwrites a farm's configured value, including a
	deliberate 0. Idempotent: safe on every install and migrate.
	"""
	if not frappe.db.table_exists("Singles"):
		return
	if not frappe.get_meta("Livestock Settings").get_field("gestation_period_days"):
		# Settings doctype not yet migrated to include the timing fields.
		return

	for fieldname, default in TIMING_DEFAULTS.items():
		if read_setting(fieldname) in (None, ""):
			frappe.db.set_single_value("Livestock Settings", fieldname, default)

	frappe.db.commit()


def after_install():
	ensure_milking_stock_entry_type()
	ensure_livestock_event_types()
	ensure_livestock_timing_defaults()
