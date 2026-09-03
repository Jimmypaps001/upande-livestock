"""Which company a livestock document belongs to.

Livestock documents are written from forms that never ask the user to pick a
company, so a value has to be found. `default_company` tries three sources in
priority order; `company_or_throw` is what write endpoints call when a blank
company would otherwise reach the doctype's own validation as a less helpful
error.
"""

import frappe
from frappe import _


def default_company():
	"""The company to stamp on livestock documents.

	Livestock Settings wins so a farm can pin its own company, then the user's
	default, then the site-wide Global Defaults value — the same last resort
	patches/migrate_animals_off_asset.py uses. Without the Global Defaults step the
	health, weight and disposal forms fail with "No company configured" on any site
	that never filled in the livestock-specific setting.
	"""
	return (
		frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		or frappe.defaults.get_user_default("company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)


def company_or_throw(company=None):
	company = company or default_company()
	if not company:
		frappe.throw(_("No company configured (Livestock Settings > Default Company)."))
	return company
