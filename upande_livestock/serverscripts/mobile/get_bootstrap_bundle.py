# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Everything the app needs before it can show a form, in one call.

Every record screen on the handset needs the same few things: who the operator
is, which herds exist, what the farm's timing settings say, which company to
book against, and what the drug and semen stores actually hold. The app was
fetching those per screen — `useOperator` on eight screens, `useHerds` on five,
`useDefaultCompany` on four, `useLivestockSettings` on three — and
`useStoreQty` made one request *per item per warehouse*, so opening the service
form cost a request for every semen straw on the shelf.

That is the shape `upande_scp.serverscripts.mobile.get_farm_data_bundle` was
built to fix, and this is the same fix: one response, one round-trip, with a
`version` the client sends back to skip the payload entirely when nothing has
moved.

Read-guarded on Herds. It discloses herd structure, store balances and the
farm's settings — not something an arbitrary logged-in user should collect.
"""

import hashlib

import frappe

from upande_livestock.serverscripts.common import herd_movement
from upande_livestock.serverscripts.common.choices import herd_label_map, select_options
from upande_livestock.serverscripts.common.company import default_company
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.event_items import (
	consumes_items,
	default_store,
	groups_for_event,
	items_for_event,
	must_name_item,
)
from upande_livestock.serverscripts.husbandry._shared import husbandry_drug_items
from upande_livestock.serverscripts.mobile._shared import digest, unchanged

# The doctypes whose state this payload reflects. A change to any of them must
# change the version, or the phone will keep serving a stale form.
# Animal is here for the beef herd cards (females and bulls per herd); it changes more
# often than the rest, which costs a re-download, not a wrong answer.
_SOURCES = ["Herds", "Animal", "Livestock Event Type", "Livestock Event Type Item Group", "Employee", "Bin", "Item"]


def beef_settings():
	"""The Beef herd settings the phone reads, with their defaults."""
	from upande_livestock.serverscripts.common.beef_settings import default_service_type, kinship_check_on
	from upande_livestock.serverscripts.common.timings import get_timing

	return {
		"calf_separation_age_days": get_timing("calf_separation_age_days"),
		"default_service_type": default_service_type(),
		"breeding_bull_min_age_months": get_timing("breeding_bull_min_age_months"),
		"conception_window_days": get_timing("conception_window_days"),
		"kinship_check": kinship_check_on(),
	}


def herd_category(h):
	"""The herd's category, worked out rather than stored.

	Herds once carried a category select, which said what the herd's age band
	already says; it is derived from `min_age` / `max_age` now.
	"""
	if h.custom_is_calf_rearing or 0 < (h.max_age or 0) <= 12:
		return "Youngstock < 12m"
	if (h.max_age or 0) > 12:
		return "Youngstock > 12m"
	return None


def counts(herd, stored):
	"""Females, bulls and fed head in a herd (calves under the separation age excluded)."""
	from upande_livestock.serverscripts.common.calf_separation import head_breakdown

	b = head_breakdown(herd)
	return {"females": b["females"], "bulls": b["bulls"], "calves": b["calves"],
	        "fed_heads": max(0, int(stored or 0) - b["calves"])}


@frappe.whitelist()
def get_bootstrap_bundle(version=None):
	def go():
		guard_read("Herds")
		settings = beef_settings()
		# The settings are a Single, which `digest` cannot see; fold them in.
		current = hashlib.sha1((digest(_SOURCES) + frappe.as_json(settings)).encode()).hexdigest()[:16]
		if unchanged(version, current):
			return {"ok": True, "unchanged": True, "version": current}

		labels = herd_label_map()

		herds = frappe.get_all(
			"Herds",
			fields=[
				"name",
				"herd_name",
				"number_of_animals",
				"bom",
				"custom_is_calf_rearing",
				"min_age",
				"max_age",
				"herd_class",
			],
			order_by="herd_name asc",
		)
		heifer = set(herd_movement.heifer_herds())
		in_calf = set(herd_movement.in_calf_herds())
		calf = set(herd_movement.calf_group_herds())
		return {
			"ok": True,
			"version": current,
			"operator": current_employee(),
			"company": default_company(),
			"warehouses": {"drug": default_store("Vaccination") or default_store("Treatment"),
			               "semen": default_store("Service")},
			"herds": [
				{
					"name": h.name,
					"label": labels.get(h.name, h.name),
					"heads": int(h.number_of_animals or 0),
					"category": herd_category(h),
					"is_heifer": h.name in heifer,
					"is_in_calf": h.name in in_calf,
					"is_calf": h.name in calf,
					"is_calf_rearing": bool(h.custom_is_calf_rearing),
					"min_age": h.min_age,
					"max_age": h.max_age,
					"has_bom": bool(h.bom),
					"herd_class": h.herd_class or "Other",
					"is_breeding": h.herd_class == "Breeding",
					**counts(h.name, h.number_of_animals),
				}
				for h in herds
			],
			"event_types": frappe.get_all(
				"Livestock Event Type",
				filters={"is_active": 1},
				fields=["name", "creates_animal", "detail_doctype"],
				order_by="name asc",
			),
			# The N+1 this bundle exists to remove: every issuable item with its
			# on-hand quantity, for the store the issue will actually draw from.
			# Each from its event types' rules (Settings → Stock).
			"drugs": husbandry_drug_items(),
			"semen": items_for_event("Service"),
			# What each event type posts, so the phone follows the same rules.
			"stock_rules": {
				t: {"groups": groups_for_event(t), "default_store": default_store(t),
				    "must_name_item": must_name_item(t)}
				for t in frappe.get_all("Livestock Event Type", filters={"is_active": 1}, pluck="name")
				if consumes_items(t)
			},
			"settings": settings,
			"options": {
				"service_types": select_options("Livestock Event", "service_type"),
				"diagnosis_results": select_options("Livestock Event", "diagnosis_result"),
				"calving_outcomes": select_options("Livestock Event", "custom_calving_outcome"),
				"abortion_causes": select_options("Livestock Event", "abortion_cause"),
				"animal_sexes": select_options("Animal", "sex"),
			},
		}

	return run(go, "livestock mobile get_bootstrap_bundle failed")
