"""Install/migrate setup for upande_livestock.

Ensures the master records the app depends on exist on every site, so a fresh
deploy doesn't fail link validation.
"""

import frappe

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


def after_install():
	ensure_milking_stock_entry_type()
