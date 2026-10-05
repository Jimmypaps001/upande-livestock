"""Scrap the Asset behind an animal that died or was culled.

Guards Asset. It had no permission check at all, and it writes off money:
a phone authenticating as a real user makes that gap a real one."""

import frappe
from frappe import _


def _scrap_livestock_asset(animal=None, asset_name=None, reason=None, scrapping_date=None):
	"""Write the animal's Asset off through ERPNext's own scrap.

	This used to build the write-off Journal Entry by hand, and got it wrong
	both ways. With no opening depreciation it credited the depreciation
	EXPENSE account instead of the fixed-asset account, so the asset stayed on
	the balance sheet and the P&L netted to nothing. With depreciation it
	debited value-after-depreciation plus only the OPENING accumulated
	depreciation against the full gross, which stops balancing the moment any
	depreciation is booked — the entry threw, the throw was swallowed, and the
	animal retired with nothing written off.

	ERPNext's steps book depreciation up to the scrap date, then post an
	"Asset Disposal" entry from its own disposal GL rules; submitting that entry
	marks the Asset Scrapped, and cancelling it restores the Asset. Called
	step by step rather than through `scrap_asset`, whose permission check
	belongs to the REST entry point below.
	"""
	from erpnext.assets.doctype.asset.depreciation import (
		create_journal_entry_for_scrap,
		depreciate_asset,
		get_note_for_scrap,
		validate_asset_for_scrap,
	)
	from frappe.utils import getdate

	animal_name = animal or asset_name
	reason = reason or ""
	scrap_date = getdate(scrapping_date or frappe.utils.today())

	if not animal_name:
		frappe.throw("animal is required")

	asset_name = frappe.db.get_value("Animal", animal_name, "asset_link")
	if not asset_name:
		frappe.throw("Animal " + str(animal_name) + " is not capitalised (no linked Asset); cannot scrap.")

	asset = frappe.get_doc("Asset", asset_name)
	validate_asset_for_scrap(asset, scrap_date)
	asset.db_set("disposal_date", scrap_date)
	depreciate_asset(asset, scrap_date, get_note_for_scrap(asset))
	asset.reload()
	create_journal_entry_for_scrap(asset, scrap_date)

	journal_entry = frappe.db.get_value("Asset", asset_name, "journal_entry_for_scrap")
	if reason and frappe.get_meta("Asset").has_field("custom_reason_for_scrapping"):
		frappe.db.set_value("Asset", asset_name, "custom_reason_for_scrapping", reason)

	# Retiring the animal is deliberately NOT done here: common.animal.retire_animal
	# is the single writer of the final Animal.status. No commit either — the
	# Disposal's own transaction carries this.
	return {
		"success": True,
		"asset": asset_name,
		"status": "Scrapped",
		"journal_entry": journal_entry,
		"reason": reason,
	}


def restore_scrapped_asset(asset_name):
	"""Undo a scrap: cancel its write-off and put the Asset back in service.

	ERPNext's own `restore_asset`, step by step for the same reason as above.
	A write-off posted by this module's old hand-built entry was a
	"Depreciation Entry", which does not reset the Asset when cancelled, so
	the status is reset here explicitly as well.
	"""
	from erpnext.assets.doctype.asset.depreciation import (
		cancel_journal_entry_for_scrap,
		get_note_for_restore,
		reset_depreciation_schedule,
		reverse_depreciation_entry_made_on_disposal,
	)

	asset = frappe.get_doc("Asset", asset_name)
	if asset.status != "Scrapped":
		return
	reverse_depreciation_entry_made_on_disposal(asset)
	reset_depreciation_schedule(asset, get_note_for_restore(asset))
	cancel_journal_entry_for_scrap(asset)
	asset.reload()
	asset.db_set({"journal_entry_for_scrap": None, "disposal_date": None})
	asset.set_status()


@frappe.whitelist()
def scrap_livestock_asset(animal=None, asset_name=None, reason=None, scrapping_date=None):
	"""REST entry point. The guard lives here, not in `_scrap_livestock_asset`.

	`_scrap_livestock_asset` is also called from
	`doctype/livestock_disposal/livestock_disposal.py` after the Disposal
	submits, inside a try/except that downgrades any failure to a toast. A guard
	in the shared function would therefore be swallowed: the animal would retire
	and the Journal Entry would silently never post. The desk path has already
	been permission-checked by the Disposal itself.

	Asset *write*, not create — this amends an existing Asset rather than making
	one. The Journal Entry and Sales Invoice it posts are inserted with
	ignore_permissions, so this is the only check standing.
	"""
	if not frappe.has_permission("Asset", "write"):
		frappe.throw(_("You are not permitted to scrap a livestock Asset."), frappe.PermissionError)
	return _scrap_livestock_asset(animal=animal, asset_name=asset_name, reason=reason, scrapping_date=scrapping_date)
