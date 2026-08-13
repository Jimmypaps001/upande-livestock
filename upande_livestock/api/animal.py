# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Shared Animal helpers used by more than one entry path.

Calf creation lives here rather than in the Livestock Event controller because
api/operations.py:record_birth already owns the multi-calf loop for the web and
mobile forms. If both created Animals independently, a birth booked through the
form would create the calf twice.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.livestock_timings import read_setting


def resolve_calf_herd():
	"""The herd a newborn calf belongs in, or None if nothing resolves.

	Order: the explicit setting, then the calf-rearing flag, then the age bracket
	configured in settings, then the Youngstock < 12m category, then the herd with
	the lowest min_age.
	"""
	explicit = frappe.db.get_single_value("Livestock Settings", "default_calf_herd")
	if explicit and frappe.db.exists("Herds", explicit):
		return explicit

	flagged = frappe.db.get_value("Herds", {"custom_is_calf_rearing": 1}, "name")
	if flagged:
		return flagged

	# read_setting, not get_single_value: these are Float fields, and
	# get_single_value casts an unset Float to 0.0 — so `is not None` would always
	# be true and this branch would silently query for a herd with min_age=0,
	# max_age=0 instead of being skipped when the setting was never configured.
	min_age = read_setting("default_calf_herd_min_age")
	max_age = read_setting("default_calf_herd_max_age")
	if min_age not in (None, "") and max_age not in (None, ""):
		bracketed = frappe.db.get_value("Herds", {"min_age": flt(min_age), "max_age": flt(max_age)}, "name")
		if bracketed:
			return bracketed

	categorised = frappe.db.get_value("Herds", {"custom_herd_category": "Youngstock < 12m"}, "name")
	if categorised:
		return categorised

	youngest = frappe.get_all("Herds", fields=["name"], order_by="min_age asc", limit=1)
	return youngest[0].name if youngest else None


def recompute_herd_count(herd):
	"""Set Herds.number_of_animals to the actual count. Matches herd_movement_processor."""
	if not herd:
		return
	count = frappe.db.count("Animal", {"current_herd": herd, "docstatus": ["!=", 2]})
	frappe.db.set_value("Herds", herd, "number_of_animals", count)


def create_calf(dam, tag_number, sex, event_date, birth_weight=None, burn_name=None, herd=None):
	"""Insert a newborn Animal and return its name.

	Throws on a duplicate tag before writing anything, so a mistyped tag cannot
	half-create a birth.
	"""
	tag = (tag_number or "").strip()
	if not tag:
		frappe.throw(_("Calf tag number is required."))
	if frappe.db.exists("Animal", tag):
		frappe.throw(_("Animal {0} already exists — pick a different calf tag.").format(tag))
	if sex not in ("Female", "Male"):
		frappe.throw(_("Calf sex must be Female or Male."))

	dam_doc = frappe.get_doc("Animal", dam)
	target_herd = herd or resolve_calf_herd()
	if not target_herd:
		frappe.throw(_("No calf herd could be resolved. Set Default Calf Herd in Livestock Settings."))

	calf = frappe.new_doc("Animal")
	calf.tag_number = tag
	calf.burn_name = burn_name or tag
	calf.sex = sex
	calf.date_of_birth = event_date
	calf.acquisition_date = event_date
	calf.current_herd = target_herd
	calf.company = dam_doc.company or frappe.db.get_single_value(
		"Livestock Settings", "custom_default_company"
	)
	calf.dam = dam
	calf.birth_weight_kg = flt(birth_weight)
	calf.origin = "Born on Farm"
	calf.status = "Active"
	calf.repro_status = "Calf"
	if dam_doc.breed:
		calf.breed = dam_doc.breed
	if dam_doc.species:
		calf.species = dam_doc.species
	calf.insert(ignore_permissions=True)

	recompute_herd_count(target_herd)
	return calf.name
