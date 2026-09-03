# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Shared Animal helpers used by more than one entry path.

Calf creation lives here, in one function, rather than duplicated in the
Livestock Event controller and in api/operations.py: every Birth event —
whether inserted from the desk form, or created by record_birth /
record_calf_births — leaves `animal` unset and lets
LivestockEvent.create_calf_if_needed() call create_calf() here. If more than
one path created Animals independently, a birth booked through any of them
could create the calf twice.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common.timings import read_setting


def resolve_calf_herd(sex=None):
	"""The herd a newborn calf belongs in, or None if nothing resolves.

	Sex decides this before anything else does. A heifer calf joins the growth
	ladder and climbs it; a bull calf goes to the bull herd, where a selling
	window may be running against it. Sending both to one herd — which is what
	happened before the Herd Movement settings existed — puts bull calves on a
	ladder built for animals that will one day be milked.

	Falling back through: the sex-specific herd, the old single Default Calf
	Herd, the calf-rearing flag, the age bracket, Youngstock < 12m, and finally
	the herd with the lowest min_age.
	"""
	from upande_livestock.serverscripts.common import herd_movement

	by_sex = herd_movement.calf_herd(sex) if sex else None
	if by_sex and frappe.db.exists("Herds", by_sex):
		return by_sex

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


# An animal with one of these statuses has left the herd. It keeps its
# `current_herd` so its history stays readable, which is precisely why every
# headcount has to exclude it explicitly.
RETIRED_STATUSES = ("Dead", "Deceased", "Sold", "Culled", "Disposed", "Transferred Out")


def live_herd_count(herd):
	"""How many animals are actually in `herd` right now.

	The count used to be every Animal row pointing at the herd, retired ones
	included — so a herd that had sold four cows still reported them, and feed
	was manufactured for animals that were no longer on the farm. A disposal
	sets the status and leaves `current_herd` alone on purpose, so the status
	filter is the only thing that can tell the difference.
	"""
	return frappe.db.count(
		"Animal",
		{
			"current_herd": herd,
			"docstatus": ["!=", 2],
			"status": ["not in", RETIRED_STATUSES],
		},
	)


def recompute_herd_count(herd):
	"""Set Herds.number_of_animals to the live count."""
	if not herd:
		return
	frappe.db.set_value("Herds", herd, "number_of_animals", live_herd_count(herd))


def create_calf(dam, tag_number, sex, event_date, birth_weight=None, burn_name=None, herd=None,
                breed=None, health_status=None, vet_remarks=None, photo=None):
	"""Insert a newborn Animal and return its name.

	Throws on a duplicate tag before writing anything, so a mistyped tag cannot
	half-create a birth.

	`breed` overrides the dam's — a calf by a different sire is not necessarily
	its mother's breed. The condition at birth is recorded on the animal because
	it is a fact about this animal on one day, not a health case to be followed.
	"""
	tag = (tag_number or "").strip()
	if not tag:
		frappe.throw(_("Calf tag number is required."))
	if frappe.db.exists("Animal", tag):
		frappe.throw(_("Animal {0} already exists — pick a different calf tag.").format(tag))
	if sex not in ("Female", "Male"):
		frappe.throw(_("Calf sex must be Female or Male."))

	dam_doc = frappe.get_doc("Animal", dam)
	target_herd = herd or resolve_calf_herd(sex)
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
	calf.breed = breed or dam_doc.breed
	if dam_doc.species:
		calf.species = dam_doc.species
	if health_status:
		calf.birth_health_status = health_status
	if vet_remarks:
		calf.birth_vet_remarks = vet_remarks
	if photo:
		calf.image = photo
	calf.insert(ignore_permissions=True)

	recompute_herd_count(target_herd)
	return calf.name


STATUS_BY_DISPOSAL_TYPE = {
	"Sold": "Sold",
	# A gift leaves the farm with no sale behind it. "Transferred Out" is the
	# one status that says exactly that; Sold would invent revenue and Culled
	# would say the animal was destroyed.
	"Gifted": "Transferred Out",
	"Culled (Farm Use)": "Culled",
	"Died — Natural Causes": "Dead",
	"Died — Disease": "Dead",
	"Died — Accident": "Dead",
	"Condemned": "Culled",
	"Slaughtered": "Culled",
}


def retire_animal(animal, disposal_type):
	"""Set the animal's final status and disable it. History is left intact."""
	status = STATUS_BY_DISPOSAL_TYPE.get(disposal_type, "Culled")
	herd = frappe.db.get_value("Animal", animal, "current_herd")
	frappe.db.set_value("Animal", animal, {"status": status, "disabled": 1}, update_modified=False)
	recompute_herd_count(herd)


# NOTE: there is deliberately no custom link query here. Frappe's default link
# search already excludes a record whose `disabled` Check field is set —
# frappe/desk/search.py:215-217:
#
#     if meta.get("fields", {"fieldname": "disabled", "fieldtype": "Check"}):
#         filters.append([doctype, "disabled", "!=", 1])
#
# so naming the field `disabled` is the whole implementation. A hand-rolled
# standard_queries function would have to re-implement user-permission
# enforcement, search_fields, title-field matching and as_dict handling, and
# would silently lose them — a permissions regression dressed up as a feature.
