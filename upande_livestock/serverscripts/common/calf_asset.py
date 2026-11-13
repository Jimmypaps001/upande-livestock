# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Every calf born on the farm goes on the fixed-asset register.

The herd is already capitalised, one ERPNext Asset per animal, linked through
`Animal.asset_link`. A calf is born into that herd and used to be missed, so the
register fell behind the animals. This gives each live-born calf an Asset of the
same shape the farm creates by hand: a 0-2 calf, bought on its birthday for a
flat value, submitted, with no depreciation and therefore no GL entry.

A BIRTH MUST NEVER FAIL BECAUSE OF THE BOOKS. Everything here runs inside a
savepoint and swallows its own failure: the calf is recorded, the failure goes
to the Error Log and the answer carries a warning so somebody raises the asset
by hand (or runs `backfill_calf_assets` once the settings are right).

Settings live in Livestock Settings, section "Calf asset".

CANCELLING A BIRTH is deliberately NOT handled. Cancelling a Birth or Calving
leaves the calf Animal in place (nothing in this app removes or retires it), so
its asset is still a true fixed asset; once a person retires or deletes the
calf, the asset is closed through the normal disposal / scrap path, which
already works from `Animal.asset_link`.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common.stock import note_warning

SAVEPOINT = "calf_asset"


def _settings():
	return frappe.get_single("Livestock Settings")


def _problem(s):
	"""What is missing from the settings, or None when an asset can be raised."""
	missing = [
		label
		for label, value in (
			(_("Item"), s.get("calf_asset_item")),
			(_("Asset Category"), s.get("calf_asset_category")),
			(_("Location"), s.get("calf_asset_location")),
		)
		if not value
	]
	if missing:
		return _("Calf asset settings are incomplete (missing {0}).").format(", ".join(missing))
	for doctype, field in (("Item", "calf_asset_item"), ("Asset Category", "calf_asset_category"),
	                       ("Location", "calf_asset_location")):
		if not frappe.db.exists(doctype, s.get(field)):
			return _("Calf asset setting {0} {1} does not exist.").format(doctype, s.get(field))
	return None


def create_calf_asset(animal, settings=None):
	"""Put one calf on the fixed-asset register. Returns the Asset name or None.

	Never raises. Skips when the switch is off, when the animal already has an
	asset, or has no date of birth. Anything else that goes wrong is logged and
	warned about, and the savepoint keeps the failed insert out of the birth.
	"""
	try:
		s = settings or _settings()
		if not s.get("create_calf_asset"):
			return None
		doc = animal if hasattr(animal, "doctype") else frappe.get_doc("Animal", animal)
		if doc.get("asset_link") or not doc.get("date_of_birth"):
			return None
		who = doc.burn_name or doc.name
		problem = _problem(s)
		if problem:
			_tell(doc, problem)
			return None

		frappe.db.savepoint(SAVEPOINT)
		try:
			asset = frappe.new_doc("Asset")
			if s.get("calf_asset_naming_series"):
				asset.naming_series = s.calf_asset_naming_series
			asset.item_code = s.calf_asset_item
			asset.asset_category = s.calf_asset_category
			asset.location = s.calf_asset_location
			asset.company = doc.company or s.get("custom_default_company")
			asset.asset_owner_company = asset.company
			asset.asset_name = who
			asset.asset_quantity = 1
			asset.purchase_date = doc.date_of_birth
			asset.available_for_use_date = doc.date_of_birth
			value = flt(s.get("calf_asset_value"))
			asset.net_purchase_amount = value
			asset.purchase_amount = value
			asset.calculate_depreciation = 0
			asset.insert(ignore_permissions=True)
			asset.submit()
			frappe.db.set_value(
				"Animal", doc.name,
				{"asset_link": asset.name, "is_capitalised": 1},
				update_modified=False,
			)
			doc.asset_link = asset.name
			doc.is_capitalised = 1
			frappe.db.release_savepoint(SAVEPOINT)
			return asset.name
		except Exception:
			frappe.db.rollback(save_point=SAVEPOINT)
			raise
	except Exception:
		frappe.log_error(message=frappe.get_traceback(), title="Livestock calf asset error")
		_tell(animal, _("ERPNext refused the asset (see Error Log)."))
		return None


def _tell(animal, reason):
	name = animal.name if hasattr(animal, "doctype") else animal
	note_warning(
		_("{0} is recorded, but was not put on the fixed-asset register: {1} Raise the asset by hand.")
		.format(name, reason)
	)


@frappe.whitelist()
def backfill_calf_assets(dry_run=1):
	"""Raise the missing assets of calves already on the farm. Manager only.

	Every Active animal born on the farm, with a date of birth and no asset.
	`dry_run` (the default) only lists them. Never run automatically.
	"""
	frappe.only_for("Livestock Manager")
	dry = frappe.parse_json(dry_run) if isinstance(dry_run, str) else dry_run
	dry = bool(int(dry)) if not isinstance(dry, bool) else dry

	rows = frappe.get_all(
		"Animal",
		filters={
			"status": "Active",
			"origin": "Born on Farm",
			"asset_link": ["is", "not set"],
			"date_of_birth": ["is", "set"],
		},
		fields=["name", "burn_name", "date_of_birth", "company"],
		order_by="date_of_birth, name",
	)
	if dry:
		return {"dry_run": 1, "count": len(rows), "animals": [r.name for r in rows]}

	s = _settings()
	made, failed = [], []
	for r in rows:
		asset = create_calf_asset(r.name, s)
		(made if asset else failed).append({"animal": r.name, "asset": asset})
	warnings = frappe.flags.get("livestock_stock_warnings") or []
	frappe.flags.livestock_stock_warnings = []
	return {"dry_run": 0, "count": len(rows), "created": len(made), "failed": [f["animal"] for f in failed],
	        "assets": made, "warnings": warnings}
